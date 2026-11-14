from app.domain.enums import Level
from app.domain.models.category import Category
from app.domain.models.incident import Incident
from app.domain.models.it_service import ITService
from app.domain.intelligence.duplicate_detector import DuplicateDetector, tokens
from tests.domain.helpers import T0, make_employee

DETECTOR = DuplicateDetector()
CATEGORY = Category("Application", "Apps", "Application", id=2)
PAYMENT = ITService("Payment", "Payments", Level.HIGH, id=1)
PRINTING = ITService("Printing", "Printers", Level.LOW, id=2)


def incident(number, title, description, service=PAYMENT):
    inc = Incident(title, description, make_employee(), CATEGORY, service,
                   Level.HIGH, Level.HIGH, 5, T0)
    inc.assign_identity(number, f"INC-{1000 + number}")
    return inc


A = incident(1, "Payment application unavailable", "Users are unable to complete transactions in the payment application")
B = incident(2, "Payment transaction failing", "Transaction attempts keep failing with an error at checkout")
C = incident(3, "Unable to make payment", "I cannot pay for my order at checkout")
PRINTER = incident(4, "Printer out of paper", "The third floor printer shows an out of paper message", PRINTING)


def tickets(matches):
    return [m.other_ticket_number for m in matches]


def test_the_three_payment_reports_flag_each_other_and_the_printer_report_does_not():
    everything = [A, B, C, PRINTER]
    assert set(tickets(DETECTOR.find_similar(A, everything))) == {"INC-1002", "INC-1003"}
    assert set(tickets(DETECTOR.find_similar(B, everything))) == {"INC-1001", "INC-1003"}
    assert set(tickets(DETECTOR.find_similar(C, everything))) == {"INC-1001", "INC-1002"}
    assert DETECTOR.find_similar(PRINTER, [A, B, C]) == []


def test_scores_follow_the_formula():
    by_ticket = {m.other_ticket_number: m.score for m in DETECTOR.find_similar(A, [B, C])}
    assert abs(by_ticket["INC-1002"] - 0.7667) < 1e-4       # 0.7 x (2/3) + 0.3
    assert abs(by_ticket["INC-1003"] - 0.65) < 1e-4         # 0.7 x (2/4) + 0.3
    assert tickets(DETECTOR.find_similar(A, [C, B])) == ["INC-1002", "INC-1003"]   # best first


def test_the_plans_short_acceptance_sentences_work_with_minimal_descriptions():
    short = [incident(n, title, "Please help") for n, title in
             enumerate(["Payment application unavailable", "Payment transaction failing",
                        "Unable to make payment"], start=21)]
    for one in short:
        assert len(DETECTOR.find_similar(one, short)) == 2


def test_a_different_problem_on_the_same_service_is_not_flagged():
    report = incident(5, "Payment report layout misaligned", "Columns overlap in the monthly report")
    assert DETECTOR.find_similar(A, [report]) == []


def test_same_wording_on_another_service_needs_a_near_identical_text():
    b_elsewhere = incident(6, B.title, B.description, PRINTING)
    assert DETECTOR.find_similar(A, [b_elsewhere]) == []                 # 0.7 x 2/3 = 0.47 < 0.5
    a_elsewhere = incident(7, A.title, A.description, PRINTING)
    assert tickets(DETECTOR.find_similar(A, [a_elsewhere])) == ["INC-1007"]   # identical text: 0.7


def test_synonyms_unify_different_words_for_the_same_problem():
    one = incident(8, "Cannot login", "Please help")
    two = incident(9, "Unable to sign in", "Please help")
    match = DETECTOR.find_similar(one, [two])[0]
    assert match.score == 1.0


def test_a_long_description_does_not_hide_a_matching_title():
    wordy = incident(10, "Payment transaction failing", " ".join(["background"] * 5 + [f"detail{i}" for i in range(40)]))
    assert tickets(DETECTOR.find_similar(B, [wordy])) == ["INC-1010"]


def test_matching_descriptions_flag_incidents_with_different_titles():
    text = "Payment gateway returns an error when customers submit a card"
    one, two = incident(11, "Gateway trouble", text), incident(12, "Card trouble", text)
    assert DETECTOR.find_similar(one, [two])[0].score == 1.0


def test_an_incident_never_matches_itself_or_unsaved_incidents():
    unsaved = Incident(A.title, A.description, make_employee(), CATEGORY, PAYMENT,
                       Level.HIGH, Level.HIGH, 5, T0)
    assert DETECTOR.find_similar(A, [A, unsaved]) == []
    assert DETECTOR.find_similar(A, []) == []


def test_tokens_removes_stopwords_and_unifies_synonyms():
    assert tokens("Can't login to the payment application") == {"FAIL", "AUTH", "PAYMENT", "application"}
    assert tokens("A printer is on the 3rd floor") == {"PRINTER", "3rd", "floor"}
    assert tokens("unable cannot") == {"FAIL"}
    assert tokens("") == set()
