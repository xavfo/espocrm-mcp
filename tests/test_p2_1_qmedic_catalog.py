"""P2-1 — QMedic entity catalog.

QMedic adds 141 entities on top of EspoCRM (clinical, billing, inventory, FHIR,
WhatsApp). The generic CRUD tools already reach them, but the model cannot guess
names like `Atencion`, `RecetaProducto` or `Prscdspnlineitem`, and `GET /Metadata`
costs ~1 MB per fetch.

`qmedic_catalog.py` is generated from QMedic's own `custom/Espo/Custom/Resources`
by `scripts/generate_qmedic_catalog.py`; the last test in this file regenerates it
and compares, so a stale catalog fails loudly instead of drifting silently.
"""
from __future__ import annotations

import importlib.util
import os
import re
from pathlib import Path

import httpx
import pytest

from qmedic_catalog import QMEDIC_ENTITIES, QMEDIC_GROUPS, QMEDIC_WORKFLOW

ROOT = Path(__file__).resolve().parents[1]

# Facts taken by hand from QMedic's metadata; the catalog must agree with them.
EXPECTED = {
    "Contact": {"label": "Paciente", "links": {"atenciones": "Atencion", "recetas": "Receta"}},
    "Atencion": {
        "label": "Atención",
        "status": "estado",
        "links": {"paciente": "Contact", "signosVitales": "SignosVitales"},
    },
    "Receta": {"links": {"recetaProductos": "RecetaProducto"}},
    "RecetaProducto": {"links": {"producto": "Product", "receta": "Receta"}},
    "SignosVitales": {"group": "clinico"},
}


# -- the generated catalog itself -------------------------------------------

def test_every_entity_has_a_known_group_and_a_label():
    for name, entry in QMEDIC_ENTITIES.items():
        assert entry["group"] in QMEDIC_GROUPS, name
        assert isinstance(entry["label"], str) and entry["label"], name


def test_every_group_has_a_workflow_hint():
    assert set(QMEDIC_GROUPS) == set(QMEDIC_WORKFLOW)
    assert all(QMEDIC_WORKFLOW.values())


def test_catalog_does_not_demand_infrastructure_fields():
    """`assignedUser`/`teams` are filled by the server; demanding them is noise."""
    boilerplate = {"assignedUser", "assignedUserId", "teams", "createdBy", "modifiedBy"}
    for name, entry in QMEDIC_ENTITIES.items():
        assert not (set(entry.get("required") or ()) & boilerplate), name


@pytest.mark.parametrize("entity,expected", EXPECTED.items())
def test_catalog_keeps_verified_qmedic_facts(entity, expected):
    entry = QMEDIC_ENTITIES[entity]

    for key, value in expected.items():
        if key == "links":
            for link, target in value.items():
                assert entry["links"][link] == target
        else:
            assert entry[key] == value


def test_atencion_enum_options_match_the_metadata():
    assert QMEDIC_ENTITIES["Atencion"]["enums"]["estado"] == [
        "Inicial",
        "Triage",
        "Observación",
        "Internamiento",
        "Tratamiento",
        "Tratamiento Ambulatorio",
        "Alta",
    ]


def test_datetime_fields_are_recorded_for_utc_conversion():
    """`Atencion.fechaIngreso` is a datetime; the catalog must know it."""
    assert "fechaIngreso" in QMEDIC_ENTITIES["Atencion"]["datetimes"]


def test_catalog_does_not_embed_record_ids():
    """QMedic fills some enums with real record IDs; they must not be committed."""
    pattern = re.compile(r"^[0-9a-f]{17}$")
    offenders = [
        (entity, field, option)
        for entity, entry in QMEDIC_ENTITIES.items()
        for field, options in (entry.get("enums") or {}).items()
        for option in options
        if pattern.match(option)
    ]

    assert offenders == []


# -- list_qmedic_entities ---------------------------------------------------

def test_listing_returns_every_entity_grouped(espo):
    result = espo.list_qmedic_entities()

    assert result["total"] == len(QMEDIC_ENTITIES)
    assert sum(group["count"] for group in result["groups"].values()) == result["total"]


def test_listing_a_group_includes_its_workflow(espo):
    result = espo.list_qmedic_entities(group="clinico")

    names = [item["entity"] for item in result["entities"]]
    assert "Atencion" in names and "Contact" in names
    assert "Invoice" not in names
    assert result["workflow"]


def test_listing_filters_by_label_or_name(espo):
    result = espo.list_qmedic_entities(query="receta")
    names = {item["entity"] for item in result["entities"]}

    assert {"Receta", "RecetaProducto", "RecetaOftalmologica"} <= names


def test_listing_unknown_group_lists_the_valid_ones(espo):
    result = espo.list_qmedic_entities(group="clinica")

    assert result["error"] == "unknown_group"
    assert "clinico" in result["groups"]


# -- describe_entity --------------------------------------------------------

def test_describe_uses_instance_metadata_when_available(espo):
    result = espo.describe_entity("Account")

    assert result["source"] == "metadata"
    assert "name" in result["required"]
    assert result["fields"]["tipoIdentificacion"]["options"] == [
        "04", "05", "06", "07", "08",
    ]


def test_describe_falls_back_to_the_catalog(espo):
    """The simulator's metadata has no QMedic entities at all."""
    result = espo.describe_entity("Atencion")

    assert result["source"] == "catalog"
    assert result["label"] == "Atención"
    assert result["statusField"] == "estado"
    assert result["links"]["paciente"] == "Contact"
    assert result["fields"]["estado"]["options"][0] == "Inicial"
    assert result["fields"]["fechaIngreso"]["type"] == "datetime"


def test_describe_hides_most_fields_until_asked(espo):
    result = espo.describe_entity("Task")

    assert "status" in result["fields"]  # enum: always shown
    assert "dateStart" in result["fields"]  # datetime: always shown
    assert "dueDate" not in result["fields"]  # date: only with all fields
    assert result["fieldCount"] >= len(result["fields"])
    assert "note" in result


def test_describe_all_fields_returns_the_rest(espo):
    result = espo.describe_entity("Account", include_all_fields=True)

    assert "note" not in result
    assert set(result["fields"]) == set(espo.get_metadata("entityDefs.Account.fields"))


def test_describe_unknown_entity_suggests_how_to_find_it(espo):
    result = espo.describe_entity("NoExiste")

    assert result["error"] == 404
    assert "list_qmedic_entities" in result["hint"]


# -- the catalog feeds validation when metadata cannot ---------------------

def test_invalid_enum_is_caught_from_the_catalog(espo, fake):
    result = espo.create_record("Atencion", {"name": "Control", "estado": "Inventado"})

    assert result["error"] == "validation_failed"
    assert result["problems"][0]["field"] == "estado"
    assert "Inicial" in result["problems"][0]["allowed"]
    assert result["rulesSource"] == "catalog"
    assert not [r for r in fake.requests if r.method == "POST"]


def test_missing_required_field_is_caught_from_the_catalog(espo, fake):
    result = espo.create_record("Certificado", {"name": "Reposo"})

    assert result["error"] == "validation_failed"
    assert {"field": "certificadoPaciente", "type": "required"} in result["problems"]
    assert result["rulesSource"] == "catalog"
    assert not [r for r in fake.requests if r.method == "POST"]


def test_required_link_multiple_accepts_the_ids_form(espo, fake):
    """`Receta` requires `idDiagnosticos`; the API receives `idDiagnosticosIds`."""
    result = espo.create_record(
        "Receta",
        {
            "name": "Receta de control",
            "idDiagnosticosIds": ["diag-1"],
            "recetaMedicacionIds": ["prod-1"],
        },
    )

    assert "error" not in result
    assert fake.records[("Receta", "receta-1")]["idDiagnosticosIds"] == ["diag-1"]


def test_qmedic_datetimes_are_converted_to_utc_without_metadata(espo, fake):
    espo.create_record(
        "Atencion", {"name": "Control", "fechaIngreso": "2026-12-01T10:00:00"}
    )

    stored = fake.records[("Atencion", "atencion-1")]
    assert stored["fechaIngreso"] == "2026-12-01 15:00:00"


# -- get_patient_summary ----------------------------------------------------

def _seed_patient(fake):
    fake.records[("Contact", "c-1")] = {
        "id": "c-1",
        "name": "Ana Pérez",
        "pacienteCedula": "0102030405",
    }
    return "c-1"


def test_patient_summary_reads_the_patient_and_each_section(espo, fake):
    contact_id = _seed_patient(fake)
    fake.links[("Contact", contact_id, "recetas")] = ["r-1"]

    result = espo.get_patient_summary(contact_id)

    assert result["patient"]["name"] == "Ana Pérez"
    assert set(result["sections"]) == {
        "atenciones", "signosVitales", "recetas", "certificados", "resultados",
    }
    assert result["sections"]["recetas"]["total"] == 1
    assert result["sections"]["atenciones"]["total"] == 0


def test_patient_summary_can_read_a_single_section(espo, fake):
    contact_id = _seed_patient(fake)

    result = espo.get_patient_summary(contact_id, sections="atenciones")

    assert list(result["sections"]) == ["atenciones"]


def test_patient_summary_rejects_unknown_links(espo, fake):
    contact_id = _seed_patient(fake)

    result = espo.get_patient_summary(contact_id, sections="atenciones,facturas")

    assert result["error"] == "unknown_link"
    assert "atenciones" in result["allowed"]


def test_patient_summary_caps_the_page_size(espo, fake):
    contact_id = _seed_patient(fake)

    result = espo.get_patient_summary(contact_id, max_items=500)

    assert result["pageSizeCapped"]["applied"] == 200


def test_patient_summary_survives_a_rejected_select(espo, fake):
    """An instance without `pacienteEdad` must not break the whole summary."""
    contact_id = _seed_patient(fake)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/Contact") and "select" in request.url.params:
            return httpx.Response(400, json={"message": "invalid select"})
        return fake.handler(request)

    espo._client = httpx.Client(
        base_url="https://crm.test/api/v1",
        transport=httpx.MockTransport(handler),
        timeout=5.0,
    )

    result = espo.get_patient_summary(contact_id)

    assert result["patient"]["name"] == "Ana Pérez"


# -- the catalog must match QMedic's metadata ------------------------------

def _metadata_root() -> Path:
    return Path(
        os.environ.get(
            "QMEDIC_METADATA",
            str(ROOT.parent / "qmedic-v4" / "custom" / "Espo" / "Custom" / "Resources"),
        )
    )


def _generator():
    path = ROOT / "scripts" / "generate_qmedic_catalog.py"
    spec = importlib.util.spec_from_file_location("generate_qmedic_catalog", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_catalog_is_up_to_date_with_qmedic_metadata():
    """Regenerate mentally: if QMedic changed, `--check` and this test both fail."""
    metadata_root = _metadata_root()
    if not (metadata_root / "metadata" / "entityDefs").is_dir():
        pytest.skip(f"QMedic metadata not available at {metadata_root}")

    generator = _generator()
    rendered = generator.render(generator.collect(metadata_root))
    current = (ROOT / "qmedic_catalog.py").read_text(encoding="utf-8")

    assert current == rendered, (
        "qmedic_catalog.py is stale; run python scripts/generate_qmedic_catalog.py"
    )
