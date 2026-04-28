"""
Test doubles for the 2026-04-27 tagging-kill overhaul.

`FakeEmailBisonClient` is a drop-in replacement for `EmailBisonClient` that
records every API call without making network requests. It also lets a
test arm specific calls to fail, which is how we simulate the "EB tag
succeeded but untag failed" race that produced the 133 dual-tag inboxes
in production.

Why a fake instead of a mock
────────────────────────────
A unittest.Mock would let you assert "tag_inbox was called once" but
won't let you reason about end-state ("inbox X has tag 'live' and not
'reserve' in EB"). The fake maintains a tiny in-memory model of EB
state — tag_inbox/untag_inbox/tag_lookup all read and mutate that
model — so test assertions can talk about the world the way the
production code does.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


class FakeEBError(Exception):
    """Stand-in for EmailBisonAPIError in tests."""


@dataclass
class _CallRecord:
    """One recorded API call."""
    method: str
    args: tuple
    kwargs: dict


@dataclass
class FakeEmailBisonClient:
    """
    In-memory fake of EmailBisonClient.

    State held:
      - `tags`       : tag-name → tag-id (auto-assigned on get_or_create)
      - `inbox_tags` : eb_account_id → set of tag_ids currently applied

    Failure injection:
      - `fail_on(method, when)` schedules the next matching call to raise
        FakeEBError. `when` can be a callable that inspects (args, kwargs)
        for fine-grained control (e.g. "fail untag_inbox for tag id 7").
    """

    # Public state — tests inspect these directly.
    tags: Dict[str, int] = field(default_factory=dict)
    inbox_tags: Dict[int, Set[int]] = field(default_factory=dict)
    calls: List[_CallRecord] = field(default_factory=list)

    # Failure injection.
    _failure_queue: List[tuple] = field(default_factory=list)
    _next_tag_id: int = field(default=1000)

    # The production code creates clients via `async with EmailBisonClient(...)`.
    # We mimic that contract.
    is_workspace_scoped: bool = True
    api_key: str = "fake-workspace-key"

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    # ------------------------------------------------------------------ tags
    async def list_tags(self) -> List[Dict[str, Any]]:
        self._record("list_tags")
        return [{"id": tag_id, "name": name} for name, tag_id in self.tags.items()]

    async def get_or_create_tag(self, name: str) -> Dict[str, Any]:
        self._record("get_or_create_tag", name)
        if name not in self.tags:
            self.tags[name] = self._next_tag_id
            self._next_tag_id += 1
        return {"id": self.tags[name], "name": name}

    async def tag_inbox(self, account_id: int, tag_id: int) -> Dict[str, Any]:
        self._maybe_fail("tag_inbox", account_id=account_id, tag_id=tag_id)
        self._record("tag_inbox", account_id=account_id, tag_id=tag_id)
        self.inbox_tags.setdefault(account_id, set()).add(tag_id)
        return {"ok": True}

    async def untag_inbox(self, account_id: int, tag_id: int) -> Dict[str, Any]:
        self._maybe_fail("untag_inbox", account_id=account_id, tag_id=tag_id)
        self._record("untag_inbox", account_id=account_id, tag_id=tag_id)
        self.inbox_tags.setdefault(account_id, set()).discard(tag_id)
        return {"ok": True}

    # ------------------------------------------------- workspace placeholders
    async def switch_workspace(self, workspace_id: int) -> bool:
        # Per-workspace fake — no-op like the scoped real client.
        self._record("switch_workspace", workspace_id=workspace_id)
        return True

    async def inter_batch_delay(self, seconds: float = 1.0):
        # No real sleep in tests.
        return None

    # ----------------------------------------------------- failure injection
    def fail_on(
        self,
        method: str,
        when: Optional[Callable[..., bool]] = None,
        message: str = "fake EB failure",
    ) -> None:
        """
        Arm one matching call to raise FakeEBError next time.
        `when` is an optional predicate(*args, **kwargs) -> bool.
        """
        self._failure_queue.append((method, when, message))

    def _maybe_fail(self, method: str, *args, **kwargs) -> None:
        for i, (target, predicate, message) in enumerate(self._failure_queue):
            if target != method:
                continue
            if predicate is None or predicate(*args, **kwargs):
                # Consume this fault and raise.
                self._failure_queue.pop(i)
                raise FakeEBError(message)

    # ---------------------------------------------------------- introspection
    def calls_named(self, method: str) -> List[_CallRecord]:
        return [c for c in self.calls if c.method == method]

    def tags_on(self, account_id: int) -> Set[str]:
        """Tag names currently applied to an inbox in the fake EB state."""
        ids = self.inbox_tags.get(account_id, set())
        id_to_name = {tag_id: name for name, tag_id in self.tags.items()}
        return {id_to_name[t] for t in ids if t in id_to_name}

    # --------------------------------------------------------------- helpers
    def _record(self, method: str, *args, **kwargs) -> None:
        self.calls.append(_CallRecord(method=method, args=args, kwargs=kwargs))
