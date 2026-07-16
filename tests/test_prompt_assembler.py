from pipeline.prompt_assembler import Brief, known_axes, section_messages


def test_brief_from_dict_defaults():
    b = Brief.from_dict({"topic": "X"})
    assert b.document_type == "report" and b.sections


def test_known_axes_lists_types():
    axes = known_axes()
    assert "report" in axes["document_type"]


def test_section_messages_include_prior_context():
    b = Brief.from_dict({"topic": "X"})
    msgs = section_messages(b, "Analysis", "- Overview: earlier text")
    joined = " ".join(m.content for m in msgs)
    assert "Analysis" in joined and "earlier text" in joined
