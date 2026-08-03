"""Validate parsed call chains by introspecting installed packages."""

import importlib
import inspect
from dataclasses import dataclass, field
from typing import Optional

from ghostcall.parser import CallInfo
from ghostcall.suggest import suggest


OK = "ok"
HALLUCINATED = "hallucinated"
MODULE_MISSING = "module_missing"
DYNAMIC = "dynamic"


@dataclass
class CheckResult:
    call: CallInfo
    status: str
    missing_attr: Optional[str] = None
    parent_display: Optional[str] = None
    suggestions: list[str] = field(default_factory=list)


_PROBE = "_ghostcall_probe_definitely_not_real_xyz123"


def _is_dynamic(obj) -> bool:
    try:
        return hasattr(obj, _PROBE)
    except Exception:
        return False


def check(call: CallInfo) -> CheckResult:
    chain = call.resolved_chain
    if not chain:
        return CheckResult(call=call, status=OK)

    root = chain[0]
    try:
        obj = importlib.import_module(root)
    except ModuleNotFoundError:
        return CheckResult(call=call, status=MODULE_MISSING, missing_attr=root)
    except Exception:
        return CheckResult(call=call, status=MODULE_MISSING, missing_attr=root)

    parent_path = [root]
    for attr in chain[1:]:
        if _is_dynamic(obj):
            return CheckResult(call=call, status=DYNAMIC)

        next_obj = None
        try:
            next_obj = getattr(obj, attr)
        except AttributeError:
            if inspect.ismodule(obj):
                try:
                    next_obj = importlib.import_module(".".join(parent_path + [attr]))
                except (ModuleNotFoundError, ImportError):
                    next_obj = None
            if next_obj is None:
                return CheckResult(
                    call=call,
                    status=HALLUCINATED,
                    missing_attr=attr,
                    parent_display=".".join(parent_path),
                    suggestions=suggest(attr, obj),
                )
        except Exception:
            return CheckResult(call=call, status=DYNAMIC)

        obj = next_obj
        parent_path.append(attr)

    return CheckResult(call=call, status=OK)
