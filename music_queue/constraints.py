"""Selection rules and inexpensive necessary feasibility checks, never relaxations."""
from collections import Counter


def selection_violations(instance, indices, complete=False):
    tracks = [instance.tracks[i] for i in indices]
    p = instance.policy
    violations = []
    for t in tracks:
        if not t.playable or any(t.id in listener.blocked for listener in instance.listeners):
            violations.append(f"Ineligible track {t.id}")
    for field, cap in (("folder", p.folder_cap), ("artist", p.artist_cap),
                       ("recording_family", p.family_cap)):
        if cap is not None:
            counts = Counter(getattr(t, field) for t in tracks if getattr(t, field) is not None)
            for group, count in counts.items():
                if count > cap:
                    violations.append(f"{field} cap {cap} exceeded for {group}")
    discoveries = sum(not any(r[a] for r in instance.acceptance) for a in indices)
    if discoveries > p.discovery_budget:
        violations.append("Discovery budget exceeded")
    if complete and p.representation == "strict":
        for u, row in enumerate(instance.acceptance):
            if sum(row[a] for a in indices) < p.required_count:
                violations.append(f"Unrepresented listener {instance.listeners[u].id}")
    return violations


def can_extend(instance, q):
    """Necessary checks prune safely; joint feasibility is decided by the solver."""
    if selection_violations(instance, q):
        return False
    if instance.policy.representation != "strict":
        return True
    slots = instance.queue_len - len(q)
    used = set(q)
    for row in instance.acceptance:
        missing = instance.policy.required_count - sum(row[i] for i in q)
        available = sum(row[i] for i in range(len(instance.tracks)) if i not in used)
        if missing > min(slots, available):
            return False
    return True
