"""The one place that turns a branch map + coverage counts into covered/total edges.

The branch map (written by instrument.write_branch_map) lists every real edge in "edges":
one entry per edge, {"id": <cover() id>, "side": "true" | "false"}. A switch label has one
edge (its true counter); its false counter only means "some other label" and is not an edge.
run_tests.py, report.py and merge_reports.py all call these functions, so the denominator
cannot differ between the console, the JSON, the CSV and the HTML reports.
"""


class MissingEdgesError(ValueError):
    pass


def map_edges(branch_map):
    """The edge list of a loaded branch map. A map written before the edge model has none."""
    edges = branch_map.get("edges")
    if edges is None:
        raise MissingEdgesError(
            "branch map has no \"edges\" list (written by an older instrument.py) — "
            "re-run src/instrument.py to regenerate it")
    return edges


def _hit(coverage, bid, side):
    return coverage.get(int(bid), {}).get(side, 0) > 0


def edge_coverage(branch_map, coverage):
    """(covered edges, total edges). coverage: {id: {"true": n, "false": n}}."""
    edges = map_edges(branch_map)
    covered = sum(1 for e in edges if _hit(coverage, e["id"], e["side"]))
    return covered, len(edges)


def sides_by_id(branch_map):
    """{id: set of sides that are edges}, e.g. {1: {"true", "false"}, 2: {"true"}}."""
    sides = {}
    for e in map_edges(branch_map):
        sides.setdefault(int(e["id"]), set()).add(e["side"])
    return sides


def row_status(branch_map, coverage):
    """{id: (edges hit, edges total)} per branch-map entry, for FULL / PARTIAL / NONE."""
    status = {}
    for e in map_edges(branch_map):
        bid = int(e["id"])
        hit, total = status.get(bid, (0, 0))
        status[bid] = (hit + _hit(coverage, bid, e["side"]), total + 1)
    return status


def status_label(hit, total):
    if total and hit == total:
        return "FULL"
    return "PARTIAL" if hit else "NONE"
