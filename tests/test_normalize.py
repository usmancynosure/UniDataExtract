from datetime import date

from unidata.normalize import (
    find_email,
    find_phone,
    normalize_academic_year,
    to_date,
    to_money,
)


def test_money_parses_common_formats():
    assert to_money("$58,212") == 58212.0
    assert to_money("58,212.00") == 58212.0
    assert to_money("$1,500 per semester") == 1500.0
    assert to_money(42000) == 42000.0
    assert to_money("") is None
    assert to_money("tuition varies") is None


def test_date_requires_a_year():
    # A full date is parsed...
    assert to_date("January 15, 2025") == date(2025, 1, 15)
    # ...but a year-less date is refused rather than guessed.
    assert to_date("November 1") is None
    assert to_date(None) is None


def test_academic_year_normalization():
    assert normalize_academic_year("2024-25") == "2024-2025"
    assert normalize_academic_year("2023–2024") == "2023-2024"
    assert normalize_academic_year("for 2025") == "2025"
    assert normalize_academic_year("") is None


def test_contact_helpers():
    assert find_phone("Call us at (570) 577-1101 today") == "(570) 577-1101"
    assert find_email("Email admissions@bucknell.edu please") == "admissions@bucknell.edu"
    assert find_email("logo@2x.png") is None
