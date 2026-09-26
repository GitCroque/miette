from datetime import date

from miette import ticket

PARAGRAPHS = (
    "Lou se réveille. Dehors, il pleut très fort sur le toit de la maison.",
    "Le chat miaule à la fenêtre. Lou lui ouvre, et ils se blottissent sous la couverture jaune.",
)


def test_raster_is_one_bit_at_printer_width():
    image = ticket.render_raster("Le chat mouillé", PARAGRAPHS, "Lou", date(2026, 9, 26))
    assert image.mode == "1"
    assert image.width == ticket.WIDTH == 512
    assert 300 < image.height < 2000


def test_two_names_fit_on_one_line():
    size = ticket.fit_size("Lou et Max", ticket.ROUNDED, 700, ticket.NAME_MAX_SIZE, ticket.TEXT_WIDTH)
    assert ticket.font(ticket.ROUNDED, size, 700).getlength("Lou et Max") <= ticket.TEXT_WIDTH


def test_raster_without_name_is_shorter():
    with_name = ticket.render_raster("Titre", PARAGRAPHS, "Lou", date(2026, 9, 26))
    without = ticket.render_raster("Titre", PARAGRAPHS, "", date(2026, 9, 26))
    assert without.height < with_name.height


def test_wrap_never_overflows():
    face = ticket.font(ticket.SERIF, ticket.BODY_SIZE)
    text = " ".join(PARAGRAPHS * 3)
    lines = ticket.wrap(text, face, ticket.TEXT_WIDTH)
    assert all(face.getlength(line) <= ticket.TEXT_WIDTH for line in lines)
    assert " ".join(lines) == text


def test_long_name_shrinks_to_fit():
    size = ticket.fit_size("Marie-Charlotte-Eugénie", ticket.ROUNDED, 700, ticket.NAME_MAX_SIZE, ticket.TEXT_WIDTH)
    assert size < ticket.NAME_MAX_SIZE


def test_french_date():
    assert ticket.french_date(date(2026, 8, 1)) == "1 août 2026"


def test_typeset_keeps_punctuation_with_its_word():
    assert ticket.typeset("Oh ! « Coucou » l'ami") == "Oh ! « Coucou » l’ami"
    face = ticket.font(ticket.SERIF, ticket.BODY_SIZE)
    text = ticket.typeset("Le petit chat saute très haut dans le ciel bleu et dit : bonjour !")
    for width in range(120, 480, 7):
        assert not any(line.startswith(("!", ":", "»")) for line in ticket.wrap(text, face, width))
