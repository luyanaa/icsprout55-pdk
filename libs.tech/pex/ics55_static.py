#!/usr/bin/env python3
# Copyright 2026 ICsprout Integrated Circuit Co., Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Static-only, clean-room facts recovered from the ICS55 RCX binary.

This module contains no binary loader and performs no dynamic probing.  The
constants and equations are the small subset recovered from static inspection:
64-bit FNV-1a variation, selector classes, built-in scalar fallback values,
and built-in layer/corner multipliers.  It deliberately does not invent ITF or
CAPTAB contents.  Callers must provide exact process-key presence when they
want the binary's hashed branch instead of its recovered fallback branch.
"""
from __future__ import annotations

import argparse
import json
from typing import Any, Dict, Iterable, Mapping, Sequence, Tuple

FNV64_OFFSET_BASIS = 0xCBF29CE484222325
FNV64_PRIME = 0x100000001B3
UINT64_MASK = 0xFFFFFFFFFFFFFFFF

HASH_DENOMINATOR = 65535.0
HASH_CENTER = 0.5
HASH_Q11_SHIFT = 11
HASH_Q9_SHIFT = 9
HASH_Q29_SHIFT = 29
HASH_Q31_SHIFT = 31

# These are the exact constants used by process_basic_models when the
# corresponding process-key lookup has no value.
SCALAR_FALLBACKS: Dict[str, float] = {
    "THICKNESS": 1.0001667048142213,
    "RPSQ": 1.00023338673991,
    "ETCH": 1.0001333638513772,
    "CRT1": 1.0001000228885328,
    "CRT2": 1.0001000228885328,
}

# These are the exact q_11 coefficients used by the hashed scalar branch.
SCALAR_Q11_COEFFICIENTS: Dict[str, float] = {
    "THICKNESS": 0.01,
    "RPSQ": 0.014,
    "ETCH": 0.008,
    "CRT1": 0.006,
    "CRT2": 0.006,
}

# Array order is [THICKNESS, RPSQ, ETCH].
LAYER_MULTIPLIERS: Dict[int, Tuple[float, float, float]] = {
    0: (1.004, 0.998, 1.002),
    1: (1.008, 1.002, 1.004),
    2: (1.012, 1.006, 1.006),
    3: (1.016, 1.008, 1.008),
    4: (1.020, 1.010, 1.010),
    # Unknown layer selectors fall through to the binary's class-1 array.
    5: (1.008, 1.002, 1.004),
}

# Array order is [THICKNESS, RPSQ, ETCH].
CORNER_MULTIPLIERS: Dict[int, Tuple[float, float, float]] = {
    0: (1.000, 1.000, 1.000),
    1: (0.994, 1.008, 1.004),
    2: (1.006, 1.012, 1.006),
    3: (0.996, 1.004, 1.002),
    4: (1.004, 1.010, 1.004),
    # Unknown corner selectors fall through to the binary's class-0 array.
    5: (1.000, 1.000, 1.000),
}

# process_basic_models has grounded field mappings for the scalar fields and
# the RPSQ-vs-width pair table.  The remaining names stay readout-only.
RECOVERED_FIELD_MAP: Dict[str, str] = {
    "THICKNESS": "thickness_um",
    "RPSQ": "resistance_ohm_per_square",
}
RECOVERED_TABLE_FIELD_MAP: Dict[str, str] = {
    "RPSQ_VS_WIDTH": "resistance_by_width",
}

UNMAPPED_SCALAR_PARAMETERS = ("ETCH", "CRT1", "CRT2", "RHO", "RPV", "AREA")
TABLE_FAMILIES = (
    "RPSQ_VS_WIDTH",
    "CRT1_VS_WIDTH",
    "CRT2_VS_WIDTH",
    "RPSQ_VS_WS",
    "RHO_VS_WT",
    "RHO_VS_WS",
    "ETCH_TABLE",
    "THICK_TABLE",
    "RPSQ_VS_SI_WIDTH",
    "CRT_VS_SI_WIDTH",
    "RPV_VS_AREA",
    "CRT1_VS_AREA",
    "CRT2_VS_AREA",
    "RPSQ_VS_WIDTH_AND_SPACING",
    "RHO_VS_WIDTH_AND_SPACING",
    "ETCH_VS_WIDTH_AND_SPACING",
    "RHO_VS_SI_WIDTH_AND_THICKNESS",
    "ETCH_VS_WIDTH_AND_LENGTH",
)

LAYER_SELECTOR_NAMES = {
    0: ("RDL", "TM"),
    1: ("M2", "M3", "M4", "M5"),
    2: ("M1",),
    3: ("NPOLY", "PPOLY"),
    4: ("NDIFF", "PDIFF"),
    5: ("unknown",),
}
CORNER_SELECTOR_NAMES = {
    0: ("TYP", "TYPICAL"),
    1: ("RCBEST",),
    2: ("RCWORST",),
    3: ("CBEST",),
    4: ("CWORST",),
    5: ("unknown",),
}


def fnv1a64(value: str) -> int:
    """Return the binary's 64-bit FNV-1a hash for UTF-8 *value*."""
    result = FNV64_OFFSET_BASIS
    for byte in value.encode("utf-8"):
        result = ((result ^ byte) * FNV64_PRIME) & UINT64_MASK
    return result


def centered_slice(hash_value: int, shift: int) -> float:
    """Return q_k(h) = centered unsigned 16-bit hash slice."""
    return (((hash_value >> shift) & 0xFFFF) / HASH_DENOMINATOR) - HASH_CENTER


def scalar_key(model_name: str, layer_name: str, parameter: str) -> str:
    """Build the exact scalar process key used by process_basic_models."""
    return "%s|%s|%s" % (model_name, layer_name, parameter)


def corner_class(model_name: str) -> int:
    """Return the recovered corner/model selector class."""
    upper = str(model_name).upper()
    for index, names in CORNER_SELECTOR_NAMES.items():
        if upper in names:
            return index
    return 5


def layer_class(layer_name: str) -> int:
    """Return the recovered layer selector class."""
    upper = str(layer_name).upper()
    for index, names in LAYER_SELECTOR_NAMES.items():
        if upper in names:
            return index
    return 5


def _available_keys(value: Iterable[str] | Mapping[str, Any] | None) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, Mapping):
        return {str(key) for key, enabled in value.items() if bool(enabled)}
    return {str(key) for key in value}


def scalar_factors(
    model_name: str,
    layer_name: str,
    present_keys: Iterable[str] | Mapping[str, Any] | None = None,
) -> Dict[str, Dict[str, Any]]:
    """Return recovered scalar factors and their provenance.

    ``present_keys`` is intentionally explicit.  A listed exact key selects
    the binary's hashed branch.  An absent key selects its recovered fallback
    constant; no process value is synthesized.
    """
    keys = _available_keys(present_keys)
    model_index = corner_class(model_name)
    layer_index = layer_class(layer_name)
    model_multiplier = CORNER_MULTIPLIERS[model_index]
    layer_multiplier = LAYER_MULTIPLIERS.get(layer_index, LAYER_MULTIPLIERS[5])
    result: Dict[str, Dict[str, Any]] = {}
    for index, parameter in enumerate(("THICKNESS", "RPSQ", "ETCH")):
        key = scalar_key(model_name, layer_name, parameter)
        available = key in keys
        hash_value = fnv1a64(key)
        base = (
            1.0 + centered_slice(hash_value, HASH_Q11_SHIFT) * SCALAR_Q11_COEFFICIENTS[parameter]
            if available
            else SCALAR_FALLBACKS[parameter]
        )
        result[parameter] = {
            "key": key,
            "available": available,
            "source": "fnv1a_q11" if available else "recovered_fallback",
            "hash_u64": "0x%016x" % hash_value,
            "base_factor": base,
            "corner_multiplier": model_multiplier[index],
            "layer_multiplier": layer_multiplier[index],
            "factor": base * model_multiplier[index] * layer_multiplier[index],
        }
    for parameter in ("CRT1", "CRT2"):
        key = scalar_key(model_name, layer_name, parameter)
        available = key in keys
        hash_value = fnv1a64(key)
        base = (
            1.0 + centered_slice(hash_value, HASH_Q11_SHIFT) * SCALAR_Q11_COEFFICIENTS[parameter]
            if available
            else SCALAR_FALLBACKS[parameter]
        )
        result[parameter] = {
            "key": key,
            "available": available,
            "source": "fnv1a_q11" if available else "recovered_fallback",
            "hash_u64": "0x%016x" % hash_value,
            "base_factor": base,
            # The binary multiplies CRT1/CRT2 by the already-computed RPSQ
            # factor, but does not apply the corner/layer arrays again.
            "corner_multiplier": 1.0,
            "layer_multiplier": 1.0,
            "factor": base,
            "combined_with_rpsq_factor": result["RPSQ"]["factor"],
            "combined_factor": base * result["RPSQ"]["factor"],
        }
    return result


def indexed_key(model_name: str, layer_name: str, family: str, index: int) -> str:
    """Build the recovered table-entry key ``model|layer|family|index``."""
    return "%s|%s|%s|%d" % (model_name, layer_name, family, index)


def width_table_factor(key: str, rpsq_factor: float) -> Dict[str, Any]:
    """Return the recovered RPSQ-vs-width entry multiplier."""
    hash_value = fnv1a64(key)
    variation = (
        1.0
        + centered_slice(hash_value, HASH_Q11_SHIFT) * 0.006
        + centered_slice(hash_value, HASH_Q29_SHIFT) * 0.002
    )
    return {
        "key": key,
        "hash_u64": "0x%016x" % hash_value,
        "variation_factor": variation,
        "rpsq_factor": float(rpsq_factor),
        "factor": variation * float(rpsq_factor),
    }


def table_variation(key: str, base_coefficient: float) -> Dict[str, Any]:
    """Return both recovered centered slices for a table-entry key."""
    hash_value = fnv1a64(key)
    return {
        "key": key,
        "hash_u64": "0x%016x" % hash_value,
        "q9": centered_slice(hash_value, HASH_Q9_SHIFT),
        "q11": centered_slice(hash_value, HASH_Q11_SHIFT),
        "q29": centered_slice(hash_value, HASH_Q29_SHIFT),
        "q31": centered_slice(hash_value, HASH_Q31_SHIFT),
        "width_spacing_factor": (
            1.0
            + centered_slice(hash_value, HASH_Q11_SHIFT) * float(base_coefficient)
            + centered_slice(hash_value, HASH_Q29_SHIFT) * 0.002
        ),
        "indexed_factor": (
            1.0
            + centered_slice(hash_value, HASH_Q9_SHIFT) * float(base_coefficient)
            + centered_slice(hash_value, HASH_Q31_SHIFT) * 0.002
        ),
        "base_coefficient": float(base_coefficient),
    }

def readout(
    model_name: str | None = None,
    layer_names: Sequence[str] | None = None,
    present_keys: Iterable[str] | Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return a JSON-ready inventory of recovered facts and optional factors."""
    output: Dict[str, Any] = {
        "schema_version": 1,
        "kind": "ics55_static_recovered_parameters",
        "execution": "static_only",
        "fnv1a64": {
            "offset_basis": "0x%016x" % FNV64_OFFSET_BASIS,
            "prime": "0x%016x" % FNV64_PRIME,
            "key_separator": "|",
            "hash_slices": {
                "q9": HASH_Q9_SHIFT,
                "q11": HASH_Q11_SHIFT,
                "q29": HASH_Q29_SHIFT,
                "q31": HASH_Q31_SHIFT,
            },
        },
        "scalar_fallbacks": dict(SCALAR_FALLBACKS),
        "scalar_q11_coefficients": dict(SCALAR_Q11_COEFFICIENTS),
        "layer_multipliers": {str(key): list(value) for key, value in LAYER_MULTIPLIERS.items()},
        "corner_multipliers": {str(key): list(value) for key, value in CORNER_MULTIPLIERS.items()},
        "layer_selectors": {str(key): list(value) for key, value in LAYER_SELECTOR_NAMES.items()},
        "corner_selectors": {str(key): list(value) for key, value in CORNER_SELECTOR_NAMES.items()},
        "recovered_field_map": dict(RECOVERED_FIELD_MAP),
        "recovered_table_field_map": dict(RECOVERED_TABLE_FIELD_MAP),
        "unmapped_scalar_parameters": list(UNMAPPED_SCALAR_PARAMETERS),
        "table_families": list(TABLE_FAMILIES),
        "notes": [
            "Absent scalar process keys use the recovered fallback constants.",
            "Listed scalar process keys use FNV-1a q_11 variation; listing a key asserts presence, not a numeric ITF value.",
            "RPSQ_VS_WIDTH entries use model|layer|family|index with q_11*0.006 + q_29*0.002, then the recovered RPSQ factor.",
            "ITF/CAPTAB numeric contents and proprietary interpolation remain unrecovered.",
        ],
    }
    if model_name is not None:
        names = list(layer_names or [])
        output["requested"] = {
            "model_name": model_name,
            "corner_class": corner_class(model_name),
            "layers": {
                layer_name: scalar_factors(model_name, layer_name, present_keys)
                for layer_name in names
            },
        }
    return output


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="model/corner token used in the exact process key")
    parser.add_argument("--layer", action="append", dest="layers", help="layer token; repeatable")
    parser.add_argument(
        "--present-key",
        action="append",
        default=[],
        help="exact recovered process key present in ITF/CAPTAB; repeatable",
    )
    args = parser.parse_args(argv)
    print(json.dumps(readout(args.model, args.layers, args.present_key), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
