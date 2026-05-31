from unidata.extractors import assemble_core, ground


def _raw():
    return {
        "overview": {
            "university_name": "Test University",
            "location": {"city": "Lewisburg", "state": "PA", "postal_code": "17837"},
            "contact": {"phone": "(570) 577-3000", "email": "admissions@test.edu"},
        },
        "tuition_breakdown": [
            {"fee_type": "Tuition", "cost": "$11,466", "currency": "USD"},
            {"fee_type": "Fees", "cost": 900, "currency": "USD"},
            {"fee_type": "Bad row", "cost": 0},  # out of range -> dropped
            {"fee_type": "", "cost": 500},  # no label -> dropped
        ],
        "admission_deadlines": [
            {"deadline_type": "Early Decision II", "deadline_date": "Jan 10, 2026", "notes": "ED II"},
            {"deadline_type": "Early Action", "deadline_date": "Nov 1", "notes": "EA"},  # dropped
        ],
    }


def test_assemble_core_normalizes_and_filters():
    core = assemble_core(_raw())
    # cost parsed to int; junk rows removed
    assert [(t.fee_type, t.cost) for t in core["tuition_breakdown"]] == [("Tuition", 11466), ("Fees", 900)]
    # only enum-mappable deadlines survive; ED II maps to Early Decision
    assert len(core["admission_deadlines"]) == 1
    assert core["admission_deadlines"][0].deadline_type.value == "Early Decision"


def test_ground_drops_unsupported_values():
    core = assemble_core(_raw())
    # Source text contains the tuition and phone but NOT the fees or email.
    source = "Annual tuition is $11,466. Reach the office at 570-577-3000."
    grounded = ground(core, source)
    costs = [t.cost for t in grounded["tuition_breakdown"]]
    assert 11466 in costs and 900 not in costs  # 900 isn't in the page -> dropped
    assert grounded["overview"].contact.phone == "(570) 577-3000"  # digits present
    assert grounded["overview"].contact.email is None  # not on the page -> nulled
