from unidata.normalize import (
    find_email,
    find_phone,
    find_postal_code,
    safe_email,
    to_cost,
    to_deadline_type,
)


def test_cost_parses_to_int():
    assert to_cost("$58,212") == 58212
    assert to_cost("58,212.00") == 58212
    assert to_cost("$1,500 per semester") == 1500
    assert to_cost(42000) == 42000
    assert to_cost(11466.0) == 11466
    assert to_cost("") is None
    assert to_cost("tuition varies") is None
    assert to_cost(True) is None  # guard against bool-as-int


def test_deadline_type_maps_to_allowed_values_only():
    assert to_deadline_type("Early Decision II") == "Early Decision"
    assert to_deadline_type("Regular Decision deadline") == "Regular Decision"
    assert to_deadline_type("Transfer applicants") == "Transfer Admission"
    # Anything outside the three allowed values is dropped (returns None).
    assert to_deadline_type("Early Action") is None
    assert to_deadline_type("Rolling") is None
    assert to_deadline_type(None) is None


def test_safe_email_rejects_malformed():
    assert safe_email("admissions@bucknell.edu") == "admissions@bucknell.edu"
    assert safe_email("not an email") is None
    assert safe_email("logo@2x.png") is None
    assert safe_email(None) is None


def test_contact_helpers():
    assert find_phone("Call us at (570) 577-1101 today") == "(570) 577-1101"
    assert find_email("Email admissions@bucknell.edu please") == "admissions@bucknell.edu"
    assert find_postal_code("Lewisburg, PA 17837") == "17837"
    assert find_postal_code("no zip here") is None
