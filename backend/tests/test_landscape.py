from hypoweaver.landscape.service import build_landscape


def test_five_evidence_cards_have_sample_statistics():
    cards = [
        dict(id=str(i), title=title, year=year, venue=venue, concepts=concepts, abstract="", included=True)
        for i, (title, year, venue, concepts) in enumerate(
            [
                ("DID green innovation", 2020, "Journal A", ["Policy", "Innovation"]),
                ("事件研究与绿色创新", 2020, "Journal A", ["Policy", "Innovation"]),
                ("中介分析", 2021, "Journal B", ["Finance"]),
                ("Instrumental variable study", 2022, "Journal B", ["Finance", "Policy"]),
                ("Threshold model", None, "Journal C", ["Finance"]),
            ]
        )
    ]
    result = build_landscape(cards)
    assert result["n_cards"] == 5 and result["unknown_year"] == 1
    assert result["years"] == [{"year": 2020, "count": 2}, {"year": 2021, "count": 1}, {"year": 2022, "count": 1}]
    assert result["venues"][0] == {"name": "Journal A", "count": 2}
    assert dict((v["name"], v["count"]) for v in result["keywords"])["policy"] == 3
    assert next(e["count"] for e in result["edges"] if {e["source"], e["target"]} == {"innovation", "policy"}) == 2
    assert [m["count"] for m in result["methods"]] == [1, 1, 1, 1, 1, 0]
    cards[0]["included"] = False
    assert build_landscape(cards)["n_cards"] == 4
