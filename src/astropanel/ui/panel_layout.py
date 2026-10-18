"""Four equal dashboard slots, even when fewer panels are selected."""


def panel_rows(selected, width=None):
    return [[(name, 1) for name in selected[start:start + 2]]
            for start in range(0, min(4, len(selected)), 2)]
