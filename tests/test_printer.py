from miette import printer

READY = (0x16, 0x12, 0x12, 0x12)  # relevé sur la TM-T88VI le 2026-09-26


def test_ready():
    state = printer.decode(*READY)
    assert state.ready and not state.paper_low


def test_paper_end():
    state = printer.decode(0x16, 0x12, 0x12, 0x12 | 0b01100000)
    assert not state.ready and state.message == "Plus de papier."


def test_paper_near_end_still_prints():
    state = printer.decode(0x16, 0x12, 0x12, 0x12 | 0b00001100)
    assert state.ready and state.paper_low


def test_cover_open():
    assert printer.decode(0x16, 0x12 | 0b100, 0x12, 0x12).message == "Le capot est ouvert."


def test_cutter_error():
    assert printer.decode(0x16, 0x12, 0x12 | 0b1000, 0x12).message == "Le massicot est bloqué."


def test_offline():
    assert not printer.decode(0x16 | 0b1000, 0x12, 0x12, 0x12).ready


def test_garbage_is_not_a_printer():
    assert not printer.decode(0xFF, 0x12, 0x12, 0x12).ready


def test_missing_host():
    assert "MIETTE_IMPRIMANTE" in printer.status("").message
