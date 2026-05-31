from unidata.config import CrawlSettings
from unidata.discover import rank_links, score_link

S = CrawlSettings()


def test_tuition_and_admissions_are_classified():
    assert score_link("https://x.edu/admissions/tuition-and-fees", "Tuition", S).category == "tuition"
    assert score_link("https://x.edu/admissions/apply", "Apply Now", S).category == "admissions"


def test_url_slug_outweighs_anchor_text():
    # A keyword in the path should beat the same keyword only in link text.
    in_path = score_link("https://x.edu/cost-of-attendance", "Details", S)
    in_text = score_link("https://x.edu/page", "Cost of attendance", S)
    assert in_path.score > in_text.score


def test_irrelevant_and_negative_links_are_dropped():
    ranked = rank_links(
        [
            ("https://x.edu/admissions/tuition", "Tuition & Fees"),
            ("https://x.edu/news/2024/story", "Campus news"),
            ("https://x.edu/athletics/schedule", "Game schedule"),
        ],
        S,
    )
    urls = [r.url for r in ranked]
    assert "https://x.edu/admissions/tuition" in urls
    assert "https://x.edu/news/2024/story" not in urls
    assert "https://x.edu/athletics/schedule" not in urls


def test_ranking_is_sorted_descending():
    ranked = rank_links(
        [
            ("https://x.edu/about/visit", "Visit"),
            ("https://x.edu/admissions/cost-of-attendance/tuition", "Tuition and fees"),
        ],
        S,
    )
    assert ranked[0].url.endswith("tuition")
    assert ranked == sorted(ranked, key=lambda r: r.score, reverse=True)
