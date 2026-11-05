from app.filename_parser import parse_survey_filename


def test_parses_the_five_user_filename_examples():
    samples = [
        ("2026-10-27 RWSP-B2-02 to GNB (US)(DI)(150) 0.87m CCTV.mp4", "RWSP-B2-02", "GNB", "UPSTREAM", "DI", "150", "0.87", "2026-10-27", "2026-10-27", None),
        ("2026-10-27 RWSP-B2-02 to GNC (US)(DI)(100) 6.40m CCTV.mp4", "RWSP-B2-02", "GNC", "UPSTREAM", "DI", "100", "6.4", "2026-10-27", "2026-10-27", None),
        ("2026-10-27 RWSP-B2-02 to GNC (US)(DI)(100) 6.40m CCTV.mov", "RWSP-B2-02", "GNC", "UPSTREAM", "DI", "100", "6.4", "2026-10-27", "2026-10-27", None),
        ("2026-8-28^29 Westlands Road G21 to S60 (DS)(CO)(225) 6.87m CCTV.mp4", "G21", "S60", "DOWNSTREAM", "CO", "225", "6.87", "2026-08-28", "2026-08-29", "Westlands Road"),
        ("2026-8-28^29 Westlands Road S76 to G38 (US)(PVC)(150) 2.67m CCTV.mkv", "S76", "G38", "UPSTREAM", "PVC", "150", "2.67", "2026-08-28", "2026-08-29", "Westlands Road"),
    ]
    for sample, start, finish, direction, material, size, length, survey_date, end_date, location in samples:
        result = parse_survey_filename(sample)
        assert result["parsed"] is True, (sample, result["error"])
        assert result["start_manhole"] == start
        assert result["finish_manhole"] == finish
        assert result["inspection_direction"] == direction
        assert result["material_code"] == material
        assert result["pipe_size_mm"] == size
        assert result["survey_length_m"] == length
        assert result["inspection_date"] == survey_date
        assert result["survey_end_date"] == end_date
        assert result["filename_location"] == location


def test_same_filename_is_deterministic_but_remains_a_separate_batch_row():
    name = "2026-10-27 RWSP-B2-02 to GNC (US)(DI)(100) 6.40m CCTV.mp4"
    first, second = parse_survey_filename(name), parse_survey_filename(name)
    assert first == second
    assert first["parsed"] is True


def test_parser_flags_unrecognized_or_invalid_filename_without_guessing():
    for name in (
        "Survey_Unknown_format.mp4",
        "2026-2-31 Node-A to Node-B (US)(DI)(150) 2m CCTV.mp4",
        "2026-10-27 Node-A to Node-B (XX)(DI)(150) 2m CCTV.mp4",
        "2026-10-27 Node-A to Node-B (US)(DI)(0) 2m CCTV.mp4",
    ):
        result = parse_survey_filename(name)
        assert result["parsed"] is False
        assert result["error"]
        assert result["start_manhole"] is None
