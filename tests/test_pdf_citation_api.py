"""Public PDF citation predicate survives changes to the shared segments module."""


def test_citation_sentence_public_api_rejects_bibliography_as_method_evidence() -> None:
    """A dropped predicate must fail here before consumers fail at import time."""
    from aha_common_utils.pdf import is_citation_sentence

    assert is_citation_sentence(
        'Kazman, “A Principled Way of Using Frameworks in Architectural Design”, '
        "IEEE Software, 46–53, March/April 2013."
    )
    assert is_citation_sentence(
        "Clements, P. et al. (2010) Documenting Software Architectures, vol. 2, pp. 41-58."
    )
    assert not is_citation_sentence("We chose Spring in 2013.")
    assert not is_citation_sentence("See pages 46–53 for further details.")
