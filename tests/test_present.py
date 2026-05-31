from unidata.present import fee_category, format_cost, group_by_category, tuition_summary
from unidata.schema import TuitionItem


def test_fee_category_buckets():
    assert fee_category("Tuition (in-state)") == "Tuition"
    assert fee_category("Mandatory Fees") == "Fees"
    assert fee_category("Room and Board") == "Housing"
    assert fee_category("Meal Plan") == "Food / Meals"
    assert fee_category("Total Cost of Attendance") == "Total / Cost of Attendance"
    assert fee_category("Marching band dues") == "Other"


def test_format_cost():
    assert format_cost(TuitionItem(fee_type="Tuition", cost=11466, currency="USD")) == "$11,466"
    assert format_cost(TuitionItem(fee_type="Tuition", cost=9000, currency="EUR")) == "9,000 EUR"
    assert format_cost(TuitionItem(fee_type="Tuition", cost=None)) == "—"


def test_tuition_summary_and_grouping():
    items = [
        TuitionItem(fee_type="Tuition", cost=11466),
        TuitionItem(fee_type="Fees", cost=900),
        TuitionItem(fee_type="Room and Board", cost=8150),
    ]
    s = tuition_summary(items)
    assert s == {"count": 3, "lowest": 900, "highest": 11466, "categories": 3}

    grouped = group_by_category(items)
    cats = [c for c, _ in grouped]
    # Housing is ordered before Tuition/Fees in the canonical order.
    assert cats.index("Housing") < cats.index("Tuition")
