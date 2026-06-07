from datetime import datetime, timezone
from math import sqrt
from typing import Dict, List, Optional, Tuple


RESIDUE_TO_AA = {
    "ALA": "A",
    "ARG": "R",
    "ASN": "N",
    "ASP": "D",
    "CYS": "C",
    "GLN": "Q",
    "GLU": "E",
    "GLY": "G",
    "HIS": "H",
    "ILE": "I",
    "LEU": "L",
    "LYS": "K",
    "MET": "M",
    "PHE": "F",
    "PRO": "P",
    "SER": "S",
    "THR": "T",
    "TRP": "W",
    "TYR": "Y",
    "VAL": "V",
}

Coord = Tuple[float, float, float]
CaAtom = Tuple[str, Optional[int], str, str, int, Coord]
BACKBONE_BREAK_CA_DISTANCE = 4.5


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def ensure_utc_iso(value: object) -> object:
    if not isinstance(value, str):
        return value

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def compact_dict(payload: Dict[str, object]) -> Dict[str, object]:
    return {
        key: value
        for key, value in payload.items()
        if value is not None and value != "" and value != []
    }


def extract_sequence_from_pdb(pdb_text: str) -> str:
    residues = []
    seen_positions = set()

    for line in pdb_text.splitlines():
        if not line.startswith("ATOM"):
            continue
        if len(line) < 27:
            continue

        residue = line[17:20].strip().upper()
        chain = line[21:22]
        position = line[22:26].strip()
        insertion_code = line[26:27].strip()
        key = (chain, position, insertion_code)
        if key in seen_positions:
            continue

        seen_positions.add(key)
        residues.append(RESIDUE_TO_AA.get(residue, "X"))

    return "".join(residues)


def extract_pdb_metrics(pdb_text: str) -> Dict[str, object]:
    atom_count = 0
    residues = set()
    chains = set()
    b_factors = []
    ca_atoms: List[CaAtom] = []
    atom_order = 0

    for line in pdb_text.splitlines():
        if not line.startswith("ATOM"):
            continue

        atom_count += 1
        atom_order += 1
        atom_name = line[12:16].strip() if len(line) >= 16 else ""

        if len(line) >= 27:
            chain = line[21:22].strip() or "_"
            position = line[22:26].strip()
            insertion_code = line[26:27].strip()
            residues.add((chain, position, insertion_code))
            chains.add(chain)
        else:
            chain = "_"
            position = ""
            insertion_code = ""

        if len(line) >= 54 and atom_name == "CA":
            try:
                coords = (
                    float(line[30:38].strip()),
                    float(line[38:46].strip()),
                    float(line[46:54].strip()),
                )
            except ValueError:
                pass
            else:
                ca_atoms.append((
                    chain,
                    _parse_optional_int(position),
                    position,
                    insertion_code,
                    atom_order,
                    coords,
                ))

        if len(line) >= 66:
            try:
                b_factors.append(float(line[60:66].strip()))
            except ValueError:
                pass

    metrics = compact_dict({
        "atom_count": atom_count if atom_count else None,
        "residue_count": len(residues) if residues else None,
        "chain_count": len(chains) if chains else None,
    })

    b_factor_summary = _summarize_b_factors(b_factors)
    metrics.update(b_factor_summary)
    metrics.update(_summarize_ca_geometry(ca_atoms))
    return metrics


def _parse_optional_int(value: str) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _summarize_ca_geometry(ca_atoms: List[CaAtom]) -> Dict[str, object]:
    if not ca_atoms:
        return {}

    coords = [atom[5] for atom in ca_atoms]
    center = (
        sum(coord[0] for coord in coords) / len(coords),
        sum(coord[1] for coord in coords) / len(coords),
        sum(coord[2] for coord in coords) / len(coords),
    )
    radius_of_gyration = sqrt(
        sum(_squared_distance(coord, center) for coord in coords) / len(coords)
    )

    distances = []
    sorted_atoms = sorted(ca_atoms, key=_ca_sort_key)
    for previous, current in zip(sorted_atoms, sorted_atoms[1:]):
        if previous[0] != current[0]:
            continue
        distances.append(sqrt(_squared_distance(previous[5], current[5])))

    summary: Dict[str, object] = {
        "radius_of_gyration": round(radius_of_gyration, 2),
    }

    if distances:
        backbone_break_count = sum(
            1 for distance in distances if distance > BACKBONE_BREAK_CA_DISTANCE
        )
        summary.update({
            "backbone_break_count": backbone_break_count,
            "ca_distance_mean": round(sum(distances) / len(distances), 2),
            "ca_distance_min": round(min(distances), 2),
            "ca_distance_max": round(max(distances), 2),
        })

    return summary


def _ca_sort_key(atom: CaAtom) -> Tuple[str, int, int, str]:
    chain, residue_number, _position, insertion_code, order, _coords = atom
    if residue_number is None:
        return (chain, 1, order, insertion_code)
    return (chain, 0, residue_number, insertion_code)


def _squared_distance(first: Coord, second: Coord) -> float:
    return (
        (first[0] - second[0]) ** 2
        + (first[1] - second[1]) ** 2
        + (first[2] - second[2]) ** 2
    )


def _summarize_b_factors(values: List[float]) -> Dict[str, object]:
    if not values:
        return {}

    mean_value = round(sum(values) / len(values), 2)
    min_value = round(min(values), 2)
    max_value = round(max(values), 2)
    summary: Dict[str, object] = {
        "mean_b_factor": mean_value,
        "min_b_factor": min_value,
        "max_b_factor": max_value,
    }

    # AlphaFold/ESMFold PDB files store pLDDT in the B-factor column.
    if mean_value > 0 and min_value >= 0 and max_value <= 100:
        summary["pLDDT"] = mean_value
        summary["mean_plddt"] = mean_value
        summary["plddt_source"] = "pdb_b_factor"

    return summary
