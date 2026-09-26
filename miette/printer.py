"""Dialogue avec l'imprimante thermique sur TCP 9100.

L'état est lu avant chaque impression par les commandes temps réel
`DLE EOT n` : on ne paie pas une histoire qui ne pourra pas sortir.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass

from escpos.exceptions import Error as EscposError
from escpos.printer import Network
from PIL import Image

# python-escpos n'a pas de profil TM-T88VI. Celui de la TM-T88V a les mêmes
# valeurs, vérifiées sur la machine : 180 dpi, 512 points, 42 colonnes.
PROFILE = "TM-T88V"


class PrinterError(Exception):
    """Problème compréhensible par un humain, affiché tel quel."""


@dataclass(frozen=True)
class Status:
    ready: bool
    message: str
    paper_low: bool = False


def decode(printer: int, offline: int, error: int, paper: int) -> Status:
    """Interprète les octets rendus par DLE EOT 1, 2, 3 et 4.

    Bits d'après la référence ESC/POS d'Epson. Chaque octet a les bits 1 et 4
    fixés à 1 et le bit 0 à 0 : un octet qui ne respecte pas ce motif ne vient
    pas d'une imprimante ESC/POS.
    """
    for byte in (printer, offline, error, paper):
        if byte & 0b10010011 != 0b00010010:
            return Status(False, "Réponse inattendue de l'imprimante.")

    paper_low = bool(paper & 0b00001100)
    if paper & 0b01100000 or offline & 0b00100000:
        return Status(False, "Plus de papier.", paper_low)
    if offline & 0b00000100:
        return Status(False, "Le capot est ouvert.", paper_low)
    if error & 0b00001000:
        return Status(False, "Le massicot est bloqué.", paper_low)
    if error & 0b01100000:
        return Status(False, "L'imprimante est en erreur : l'éteindre et la rallumer.", paper_low)
    if printer & 0b00001000:
        return Status(False, "L'imprimante est hors ligne.", paper_low)
    message = "Prête, mais le rouleau touche à sa fin." if paper_low else "Prête."
    return Status(True, message, paper_low)


def status(host: str, port: int = 9100, timeout: float = 3.0) -> Status:
    if not host:
        return Status(False, "Adresse de l'imprimante absente (MIETTE_IMPRIMANTE).")
    answers = []
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            for n in (1, 2, 3, 4):
                sock.sendall(bytes([0x10, 0x04, n]))
                answer = sock.recv(1)
                if not answer:
                    raise OSError("connexion fermée")
                answers.append(answer[0])
    except OSError:
        return Status(False, "Imprimante injoignable : est-elle allumée ?")
    return decode(*answers)


def connect(host: str, port: int = 9100) -> Network:
    return Network(host, port=port, timeout=10, profile=PROFILE)


def print_image(host: str, port: int, image: Image.Image) -> None:
    try:
        printer = connect(host, port)
        printer.image(image, impl="bitImageRaster", center=False)
        printer.cut()
        printer.close()
    except (OSError, EscposError) as exc:
        raise PrinterError("L'impression a échoué en cours de route.") from exc
