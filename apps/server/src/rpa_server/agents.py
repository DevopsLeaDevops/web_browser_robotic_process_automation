"""對外 Agent API 的用戶端（M14，ADR 0017）：金鑰、權限範圍、使用限制與稽核紀錄。

- 每個 Agent 系統是一個 API 用戶端，請求帶 ``Authorization: Bearer <API 金鑰>``。金鑰只在建立與
  重新產生時回傳一次，資料庫只存雜湊（同裝置權杖，:func:`rpa_server.dispatch.hash_token`）。
- 權限範圍見 :data:`SCOPES`；新用戶端只有讀取（:data:`DEFAULT_SCOPES`），發布要個別勾選。
- 其他限制在 :class:`ClientPolicy`：可用的領域與專案（None 不限）、可以開調試的錄製端（預設無）、
  執行位置與可以指定的 Worker、限額、回傳頁面內容（預設關）、到期與來源 IP。
- 稽核：每個寫入請求記一筆（:meth:`AgentService.record_audit`），只增不改；用戶端刪除後仍保留。
- 建立場景、存版本的冪等鍵記在記憶體（:meth:`AgentService.recall`），伺服器重新啟動後就忘了；
  驗證與執行的冪等鍵存在運行紀錄裡。

路由在 :mod:`rpa_server.agent_api`（專案在 :mod:`rpa_server.agent_projects`）；管理後台的 API 在
``/api/agents``。
"""

import ipaddress
import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Final, cast

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from rpa_server.dispatch import hash_token
from rpa_server.domain import DOMAIN_ID, LOCAL_WORKER, Target, now
from rpa_server.errors import ServiceError, conflict, invalid, not_found
from rpa_server.i18n import t
from rpa_server.models import ApiAudit, ApiClient, Domain, Project, Recorder, RemoteWorker, Run

__all__ = [
    "AUDIT_LIMIT",
    "DEFAULT_SCOPES",
    "KEY_PREFIX",
    "SCOPES",
    "AgentService",
    "ApiClientRecord",
    "AuditRecord",
    "ClientPolicy",
]

SCOPES: Final = (
    "scenes:read",
    "scenes:write",
    "debug",
    "files:write",
    "runs:validate",
    "scenes:publish",
    "runs:execute",
    "runs:read",
    "projects:read",
    "projects:write",
    "projects:publish",
)
"""權限範圍，依 Agent 做事的順序：先做場景，再把場景組成專案裡的組合場景。"""
DEFAULT_SCOPES: Final = ("scenes:read", "runs:read", "projects:read")
KEY_PREFIX: Final = "rpa_ak_"
"""API 金鑰的開頭：一眼看得出是哪一種權杖（不要和裝置權杖混用）。"""
AUDIT_LIMIT: Final = 200
_TOUCH_SECONDS: Final = 60.0
"""「最後使用」最多每分鐘寫一次資料庫。"""
_RECALL_SECONDS: Final = 24 * 3600.0
_RECALL_SIZE: Final = 2000


@dataclass(frozen=True, slots=True)
class ClientPolicy:
    """用戶端能做什麼：權限範圍以外的限制。清單是 None 時不限。"""

    scopes: tuple[str, ...] = DEFAULT_SCOPES
    domains: tuple[str, ...] | None = None
    """可以讀寫哪些領域的場景（組合場景放在哪個領域資料夾也算）。"""
    projects: tuple[str, ...] | None = None
    """可以讀寫哪些專案的組合場景；限定時不能新增專案。"""
    recorders: tuple[str, ...] = ()
    """可以在哪幾台錄製端開調試瀏覽器；錄製端本身也要允許 Agent 調試。"""
    target: Target | None = None
    """驗證與執行的位置；None 時跟隨伺服器的預設執行位置，Agent 可以自己指定。"""
    workers: tuple[str, ...] | None = None
    """可以指定（workerId）哪幾台 Worker；local 是伺服器本機。"""
    max_debug_sessions: int = 2
    max_queued_runs: int = 20
    page_content: bool = False
    """截圖、頁面結構、錄影與報告能不能給這個用戶端。"""
    allowed_ips: tuple[str, ...] | None = None
    """允許的來源 IP 或網段（CIDR）。"""
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ApiClientRecord:
    id: str
    name: str
    description: str | None
    key_prefix: str
    policy: ClientPolicy
    disabled: bool
    created_at: datetime
    last_used_at: datetime | None

    def can(self, scope: str) -> bool:
        return scope in self.policy.scopes

    def require(self, *scopes: str) -> None:
        """要有其中一個權限範圍，沒有就 403 ``scope_missing``。"""
        if not any(self.can(scope) for scope in scopes):
            raise ServiceError(
                403,
                "scope_missing",
                t("error.agent_scope_missing", scopes=" / ".join(scopes)),
                scopes=list(scopes),
            )

    def domain_allowed(self, domain_id: str | None) -> bool:
        domains = self.policy.domains
        return domains is None or (domain_id is not None and domain_id in domains)

    def project_allowed(self, project_id: str | None) -> bool:
        """不屬於任何專案的組合場景（專案管理裡列出的）不給 Agent。"""
        projects = self.policy.projects
        return project_id is not None and (projects is None or project_id in projects)

    def to_json(self) -> dict[str, object]:
        policy = self.policy
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "keyPrefix": self.key_prefix,
            "scopes": list(policy.scopes),
            "domains": list(policy.domains) if policy.domains is not None else None,
            "projects": list(policy.projects) if policy.projects is not None else None,
            "recorders": list(policy.recorders),
            "target": policy.target,
            "workers": list(policy.workers) if policy.workers is not None else None,
            "limits": {
                "debugSessions": policy.max_debug_sessions,
                "queuedRuns": policy.max_queued_runs,
            },
            "pageContent": policy.page_content,
            "allowedIps": list(policy.allowed_ips) if policy.allowed_ips is not None else None,
            "expiresAt": _iso(policy.expires_at),
            "disabled": self.disabled,
            "createdAt": _iso(self.created_at),
            "lastUsedAt": _iso(self.last_used_at),
        }


@dataclass(frozen=True, slots=True)
class AuditRecord:
    id: int
    at: datetime
    client_id: str
    client_name: str
    method: str
    action: str
    target: str | None
    status: int
    code: str | None
    ip: str | None

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "at": _iso(self.at),
            "clientId": self.client_id,
            "clientName": self.client_name,
            "method": self.method,
            "action": self.action,
            "target": self.target,
            "status": self.status,
            "code": self.code,
            "ip": self.ip,
        }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value is not None else None


def _names(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in cast("list[object]", value or []))


def _record(row: ApiClient) -> ApiClientRecord:
    policy = ClientPolicy(
        scopes=_names(row.scopes),
        domains=_names(row.domains) if row.domains is not None else None,
        projects=_names(row.projects) if row.projects is not None else None,
        recorders=_names(row.recorders),
        target=cast("Target | None", row.target),
        workers=_names(row.workers) if row.workers is not None else None,
        max_debug_sessions=row.max_debug_sessions,
        max_queued_runs=row.max_queued_runs,
        page_content=row.page_content,
        allowed_ips=_names(row.allowed_ips) if row.allowed_ips is not None else None,
        expires_at=row.expires_at,
    )
    return ApiClientRecord(
        id=row.id,
        name=row.name,
        description=row.description,
        key_prefix=row.key_prefix,
        policy=policy,
        disabled=row.disabled,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
    )


def _audit_record(row: ApiAudit) -> AuditRecord:
    return AuditRecord(
        id=row.id,
        at=row.at,
        client_id=row.client_id,
        client_name=row.client_name,
        method=row.method,
        action=row.action,
        target=row.target,
        status=row.status,
        code=row.code,
        ip=row.ip,
    )


def _unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value.strip() for value in values if value.strip()))


def _unauthorized() -> ServiceError:
    return ServiceError(401, "unauthorized", t("error.agent_unauthorized"))


def _ip_allowed(ip: str | None, allowed: Sequence[str]) -> bool:
    if ip is None:
        return False
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(address in ipaddress.ip_network(item, strict=False) for item in allowed)


@dataclass(slots=True)
class _Remembered:
    value: dict[str, object]
    at: float = field(default_factory=time.monotonic)


class AgentService:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions
        self._lock = threading.Lock()
        self._recall: OrderedDict[tuple[str, str, str], _Remembered] = OrderedDict()

    # ------------------------------------------------------------ 用戶端

    @staticmethod
    def _row(session: Session, client_id: str) -> ApiClient:
        row = session.get(ApiClient, client_id)
        if row is None:
            raise not_found("agent_not_found", t("error.agent_not_found", id=client_id))
        return row

    def list_clients(self) -> list[ApiClientRecord]:
        with self.sessions() as session:
            rows = session.scalars(select(ApiClient).order_by(ApiClient.created_at, ApiClient.id))
            return [_record(row) for row in rows]

    def names(self) -> dict[str, str]:
        """用戶端代號 → 名稱（運行列表顯示由哪個 Agent 觸發）。"""
        with self.sessions() as session:
            return {
                row.id: row.name for row in session.execute(select(ApiClient.id, ApiClient.name))
            }

    def get_client(self, client_id: str) -> ApiClientRecord:
        with self.sessions() as session:
            return _record(self._row(session, client_id))

    def create_client(
        self,
        client_id: str,
        name: str | None = None,
        description: str | None = None,
        policy: ClientPolicy | None = None,
    ) -> tuple[ApiClientRecord, str]:
        """登記一個用戶端，回傳紀錄與 API 金鑰（只有這一次拿得到）。"""
        client_id = client_id.strip()
        if not DOMAIN_ID.fullmatch(client_id):
            raise invalid("agent_id_invalid", t("error.agent_id_invalid", id=client_id))
        key = KEY_PREFIX + secrets.token_urlsafe(32)
        with self.sessions() as session:
            if session.get(ApiClient, client_id) is not None:
                raise conflict("agent_exists", t("error.agent_exists", id=client_id))
            checked = self._check(session, policy or ClientPolicy())
            row = ApiClient(
                id=client_id,
                name=(name or "").strip()[:100] or client_id,
                description=(description or "").strip()[:2000] or None,
                key_hash=hash_token(key),
                key_prefix=key[: len(KEY_PREFIX) + 4],
                disabled=False,
                created_at=now(),
            )
            self._apply(row, checked)
            session.add(row)
            session.commit()
            return _record(row), key

    def update_client(
        self,
        client_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        disabled: bool | None = None,
        policy: ClientPolicy | None = None,
    ) -> ApiClientRecord:
        """改名稱、說明、停用，或整組限制（policy）；停用後金鑰立刻失效。"""
        with self.sessions() as session:
            row = self._row(session, client_id)
            if name is not None and name.strip():
                row.name = name.strip()[:100]
            if description is not None:
                row.description = description.strip()[:2000] or None
            if disabled is not None:
                row.disabled = disabled
            if policy is not None:
                self._apply(row, self._check(session, policy))
            session.commit()
            return _record(row)

    def rotate_key(self, client_id: str) -> tuple[ApiClientRecord, str]:
        """重新產生金鑰：舊的立刻失效。"""
        key = KEY_PREFIX + secrets.token_urlsafe(32)
        with self.sessions() as session:
            row = self._row(session, client_id)
            row.key_hash = hash_token(key)
            row.key_prefix = key[: len(KEY_PREFIX) + 4]
            session.commit()
            return _record(row), key

    def delete_client(self, client_id: str) -> None:
        """刪除用戶端；它觸發的運行與稽核紀錄保留。"""
        with self.sessions() as session:
            session.delete(self._row(session, client_id))
            session.commit()
        with self._lock:
            for key in [key for key in self._recall if key[0] == client_id]:
                del self._recall[key]

    @staticmethod
    def _check(session: Session, policy: ClientPolicy) -> ClientPolicy:
        """檢查並整理限制：權限範圍、領域、專案、錄製端、Worker 要存在，IP 要寫得對。"""
        scopes = _unique(policy.scopes)
        unknown = [scope for scope in scopes if scope not in SCOPES]
        if unknown:
            raise invalid(
                "agent_scope_invalid", t("error.agent_scope_invalid", scopes=", ".join(unknown))
            )
        domains = _unique(policy.domains) if policy.domains is not None else None
        missing = [d for d in domains or () if session.get(Domain, d) is None]
        if missing:
            raise invalid(
                "agent_domain_unknown", t("error.agent_domain_unknown", ids=", ".join(missing))
            )
        projects = _unique(policy.projects) if policy.projects is not None else None
        missing = [p for p in projects or () if session.get(Project, p) is None]
        if missing:
            raise invalid(
                "agent_project_unknown", t("error.agent_project_unknown", ids=", ".join(missing))
            )
        recorders = _unique(policy.recorders)
        missing = [r for r in recorders if session.get(Recorder, r) is None]
        if missing:
            raise invalid(
                "agent_recorder_unknown", t("error.agent_recorder_unknown", ids=", ".join(missing))
            )
        workers = _unique(policy.workers) if policy.workers is not None else None
        missing = [
            w for w in workers or () if w != LOCAL_WORKER and session.get(RemoteWorker, w) is None
        ]
        if missing:
            raise invalid(
                "agent_worker_unknown", t("error.agent_worker_unknown", ids=", ".join(missing))
            )
        allowed = _unique(policy.allowed_ips) if policy.allowed_ips is not None else None
        for item in allowed or ():
            try:
                ipaddress.ip_network(item, strict=False)
            except ValueError:
                raise invalid("agent_ip_invalid", t("error.agent_ip_invalid", value=item)) from None
        return replace(
            policy,
            scopes=tuple(scope for scope in SCOPES if scope in scopes),
            domains=domains,
            projects=projects,
            recorders=recorders,
            workers=workers,
            allowed_ips=allowed or None,
        )

    @staticmethod
    def _apply(row: ApiClient, policy: ClientPolicy) -> None:
        row.scopes = list(policy.scopes)
        row.domains = list(policy.domains) if policy.domains is not None else None
        row.projects = list(policy.projects) if policy.projects is not None else None
        row.recorders = list(policy.recorders)
        row.target = policy.target
        row.workers = list(policy.workers) if policy.workers is not None else None
        row.max_debug_sessions = policy.max_debug_sessions
        row.max_queued_runs = policy.max_queued_runs
        row.page_content = policy.page_content
        row.allowed_ips = list(policy.allowed_ips) if policy.allowed_ips is not None else None
        row.expires_at = policy.expires_at

    # ------------------------------------------------------------ 認證

    def authenticate(self, key: str | None, ip: str | None) -> ApiClientRecord:
        """依 API 金鑰找出用戶端；金鑰不對、停用、到期或來源 IP 不在允許清單時 401。"""
        if not key or not key.startswith(KEY_PREFIX):
            raise _unauthorized()
        moment = now()
        with self.sessions() as session:
            row = session.scalars(
                select(ApiClient).where(ApiClient.key_hash == hash_token(key))
            ).first()
            if row is None or row.disabled:
                raise _unauthorized()
            if row.expires_at is not None and row.expires_at <= moment:
                raise _unauthorized()
            if row.allowed_ips is not None and not _ip_allowed(ip, _names(row.allowed_ips)):
                raise _unauthorized()
            last = row.last_used_at
            if last is None or moment - last > timedelta(seconds=_TOUCH_SECONDS):
                row.last_used_at = moment
                session.commit()
            return _record(row)

    # ------------------------------------------------------------ 稽核

    def record_audit(
        self,
        client: ApiClientRecord,
        *,
        method: str,
        action: str,
        target: str | None,
        status: int,
        code: str | None,
        ip: str | None,
    ) -> None:
        with self.sessions() as session:
            session.add(
                ApiAudit(
                    at=now(),
                    client_id=client.id,
                    client_name=client.name,
                    method=method[:10],
                    action=action[:200],
                    target=target[:300] if target else None,
                    status=status,
                    code=code[:60] if code else None,
                    ip=ip[:64] if ip else None,
                )
            )
            session.commit()

    def list_audit(
        self, *, client_id: str | None = None, before: int | None = None, limit: int = AUDIT_LIMIT
    ) -> list[AuditRecord]:
        """稽核紀錄，新的在前；``before`` 是上一頁最後一筆的 id。"""
        statement = select(ApiAudit).order_by(ApiAudit.id.desc()).limit(limit)
        if client_id is not None:
            statement = statement.where(ApiAudit.client_id == client_id)
        if before is not None:
            statement = statement.where(ApiAudit.id < before)
        with self.sessions() as session:
            return [_audit_record(row) for row in session.scalars(statement)]

    # ------------------------------------------------------------ 冪等鍵

    def run_for_key(self, key: str) -> str | None:
        """用這個冪等鍵（已經加上用戶端）排入的運行。"""
        with self.sessions() as session:
            return session.scalars(select(Run.id).where(Run.idempotency_key == key)).first()

    def recall(self, client_id: str, kind: str, key: str | None) -> dict[str, object] | None:
        """同一個用戶端、同一種操作用過這個冪等鍵時，上次的回應。"""
        if not key:
            return None
        with self._lock:
            self._expire()
            found = self._recall.get((client_id, kind, key))
            return found.value if found is not None else None

    def remember(
        self, client_id: str, kind: str, key: str | None, value: dict[str, object]
    ) -> None:
        if not key:
            return
        with self._lock:
            self._recall[(client_id, kind, key)] = _Remembered(value)
            self._recall.move_to_end((client_id, kind, key))
            while len(self._recall) > _RECALL_SIZE:
                self._recall.popitem(last=False)

    def _expire(self) -> None:
        limit = time.monotonic() - _RECALL_SECONDS
        while self._recall:
            key, item = next(iter(self._recall.items()))
            if item.at >= limit:
                break
            del self._recall[key]
