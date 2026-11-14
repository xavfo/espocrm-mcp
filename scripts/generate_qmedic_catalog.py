#!/usr/bin/env python3
"""Genera `qmedic_catalog.py` a partir del metadata de una instancia QMedic.

El catálogo no reemplaza al metadata de la instancia: es el mapa que permite al
modelo saber qué entidades existen en QMedic, cómo se llaman en la interfaz y qué
campos son obligatorios o cerrados, **antes** de gastar una llamada a `GET /Metadata`
(que en 7.5.6 pesa cerca de 1 MB). La instancia sigue siendo la autoridad: si el
catálogo y el metadata discrepan, gana el metadata.

Uso:

    python scripts/generate_qmedic_catalog.py
    python scripts/generate_qmedic_catalog.py --check
    python scripts/generate_qmedic_catalog.py --metadata <ruta>/custom/Espo/Custom/Resources

`--check` compara el archivo versionado con lo que se generaría y termina con
código 1 si está desactualizado, sin escribir nada.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "qmedic_catalog.py"

# Ruta por defecto al metadata de QMedic: variable de entorno, o el repositorio
# hermano en la misma carpeta que este proyecto.
DEFAULT_METADATA = Path(
    os.environ.get(
        "QMEDIC_METADATA",
        str(
            ROOT.parent
            / "qmedic-v4"
            / "custom"
            / "Espo"
            / "Custom"
            / "Resources"
        ),
    )
)

# Campos de infraestructura que no ayudan a descubrir un dominio y que aparecen en
# casi todas las entidades. Se omiten de `links` para que el catálogo no repita lo
# mismo 141 veces.
BOILERPLATE_LINKS = {
    "createdBy", "modifiedBy", "assignedUser", "teams", "meetings", "calls",
    "emails", "tasks", "notes", "documents", "opportunities", "leads",
}

BOILERPLATE_FIELDS = {
    "assignedUser", "teams", "createdBy", "modifiedBy", "createdAt", "modifiedAt",
}

# Los IDs de EspoCRM son 17 caracteres hexadecimales en minúscula.
RECORD_ID_PATTERN = re.compile(r"^[0-9a-f]{17}$")

# Agrupación funcional. Es lo único escrito a mano: el resto sale del metadata.
# Una entidad no listada cae en "otros", y la comprobación de cobertura avisa.
GROUPS: dict[str, tuple[str, set[str]]] = {
    "clinico": (
        "Atención de pacientes: historia, signos vitales, diagnósticos y órdenes.",
        {
            "Contact", "Atencion", "Actividad", "SignosVitales", "Sesion",
            "Procedimiento", "ProtocoloCIAP", "IdDiagnostico", "Certificado",
            "Consentimiento", "ConsentimientoMotivo", "OrdenDeTrabajo",
            "Categoria", "Condicion", "Interaccion",
        },
    ),
    "especialidad": (
        "Datos de una especialidad concreta (antropometría, oftalmología, "
        "odontología, salud mental, vacunas, obstetricia).",
        {
            "AgudezaVisual", "Anticonceptivo", "Fum", "IMC", "Nutricion",
            "PesoTalla", "Percentil", "Fisico", "TractoGenital", "FichaPrueba",
            "PreguntaPruebaS", "RespuestaPruebaS", "PruebaSicolgica",
            "ExamenPsiquiatrico", "Resultados", "Valor", "Inmunizacin", "Vacuna",
            "VaccinationProtocol", "Medicationlist", "Odontograma", "Diente",
            "TratamientoOdontologico", "RecetaOftalmologica",
        },
    ),
    "recetas": (
        "Prescripciones y sus líneas: lo que el paciente debe tomar o aplicarse.",
        {
            "Receta", "RecetaProducto", "Prescription", "Prscdspnlineitem",
            "Prscpackage",
        },
    ),
    "facturacion": (
        "Facturación, cotizaciones, precios y pagos.",
        {
            "Invoice", "InvoiceItem", "Quote", "QuoteItem", "SalesOrder",
            "SalesOrders", "SalesOrderDetails", "Pago", "Precio", "Prices",
            "PaymentTerms", "TaxGroups", "TaxTypes", "TaxGroup", "Tarifario",
            "FacturacionSecuencial", "ParametrosFactura", "CreditStatus",
            "DocElectronicos", "DebtorTrans", "DebtorTransDetails", "Reflines",
            "TransTaxDetails", "SalesGroup", "SalesPoint", "SalesType",
        },
    ),
    "inventario": (
        "Productos, proveedores, bodegas y movimientos de existencias.",
        {
            "Product", "ProductCategory", "ProductBrand", "Supplier", "Supply",
            "Proveedor", "Pedido", "Compra", "ItemUnits", "StockMoves", "LocStock",
            "Location", "ShippingProvider", "Courier", "Pharmacies",
        },
    ),
    "contabilidad": (
        "Contabilidad y tesorería.",
        {
            "Asientos", "GlTrans", "LibroDiario", "LibroMayor", "Cuentas",
            "CuentasCategoria", "CuentaBancaria", "CuentaEmpresa", "Dimensions",
            "FiscalYear", "UbicacionActivosFijos", "ChartClass", "ChartMaster",
            "ChartTypes",
        },
    ),
    "comercial": (
        "Cuentas, convenios y aseguradoras con las que se factura.",
        {
            "Account", "Lead", "Case", "EmpresaMedicinaPrepagada",
            "MedicinaPrepagada", "Convenio", "Contrato", "Prestador", "Area",
            "Red", "BranchOffice", "CustBranch", "Oficina", "Company",
            "Campaign", "Subscriptionplan", "Plan",
        },
    ),
    "comunicaciones": (
        "Mensajería de WhatsApp y llamadas.",
        {
            "GruposWhatsapp", "Wischat", "Whatsapp", "VoipMessage",
            "MensajeWhastappMasivo",
        },
    ),
    "fhir": (
        "Motor de interoperabilidad FHIR y su configuración.",
        {
            "FhirConst", "FhirDependent", "FhirGroup", "FhirInput", "FhirMap",
            "FhirParameter", "FhirRule", "FhirSource", "FhirStructure",
            "FhirTarget", "Sync",
        },
    ),
    "actividad": (
        "Reuniones, llamadas, tareas y correos (núcleo de EspoCRM).",
        {"Meeting", "Call", "Task", "Email", "Document", "Recurrente"},
    ),
    "administracion": (
        "Usuarios, equipos, personal y reportes.",
        {"User", "Team", "Member", "Empleado", "Report", "ReportCategory"},
    ),
}

# Estrategia mínima de lectura para el asistente, por grupo. Se emite como texto
# para que el modelo sepa por dónde entrar en un CRM clínico en lugar de adivinar.
WORKFLOW: dict[str, str] = {
    "clinico": (
        "La historia clínica cuelga de Contact, cuya etiqueta es «Paciente». Para "
        "atender un caso: busca el paciente por `pacienteCedula` o por nombre, lista "
        "su enlace `atenciones` y entra en la Atencion, que enlaza `signosVitales`, "
        "`procedimientos` y `protocoloCIAPs`. Las recetas no cuelgan de la Atencion: "
        "están en el enlace `recetas` del propio Contact."
    ),
    "especialidad": (
        "Cada especialidad guarda sus mediciones en su propia entidad y las enlaza "
        "al paciente o a la consulta. Los rangos de referencia de antropometría "
        "están en Percentil y en las entidades de cada especialidad, no en las "
        "«Chart*», que son el plan de cuentas contable."
    ),
    "recetas": (
        "Receta es la cabecera (enlaza `contact`, `meeting` e `idDiagnosticos`) y "
        "RecetaProducto la línea, con `producto` y `receta`. Prescription, "
        "Prscpackage y Prscdspnlineitem son un modelo de prescripción alterno: "
        "comprueba con `describe_entity` cuál usa la instancia antes de escribir."
    ),
    "facturacion": (
        "Invoice es la factura y su enlace `items` las líneas; InvoiceItem lleva "
        "`taxTypes` y `transTaxDetails`. Quote/QuoteItem es la cotización. Los "
        "impuestos y las condiciones de pago se referencian por ID, así que lista "
        "TaxGroups y PaymentTerms antes de crear una factura."
    ),
    "inventario": (
        "Product es el artículo; Product.precios enlaza Precio y StockMoves "
        "registra cada movimiento con `product` y `location`, mientras LocStock "
        "guarda el saldo por bodega. No escribas StockMoves sin un motivo de "
        "movimiento válido."
    ),
    "contabilidad": (
        "El plan de cuentas es ChartClass -> ChartTypes -> ChartMaster. Asientos es "
        "el asiento y GlTrans sus líneas; LibroDiario y LibroMayor son los libros. "
        "Estas entidades suelen ser de solo lectura para un usuario de API."
    ),
    "comercial": (
        "Account es la cuenta de facturación y el paciente la referencia con "
        "`cuentaFacturacion`; el paciente es Contact, nunca Account. Convenio, "
        "Contrato, Prestador y MedicinaPrepagada formalizan la tarifa."
    ),
    "comunicaciones": (
        "Wischat/GruposWhatsapp configuran la mensajería; MensajeWhastappMasivo "
        "registra los envíos masivos. Enviar mensajes reales tiene efecto externo: "
        "confirma con el usuario antes de crear un envío."
    ),
    "fhir": (
        "Estas entidades configuran el mapeo FHIR. Leer está bien; escribir puede "
        "romper la interoperabilidad, así que pide confirmación explícita."
    ),
    "actividad": (
        "Meeting es la consulta (su etiqueta en QMedic es «Consulta»), junto con "
        "Call y Task. Se asignan al usuario de la API cuando no se indica otro "
        "(ESPO_AUTO_ASSIGN) y pueden colgar de un paciente con `parent`."
    ),
    "administracion": (
        "Usuarios, equipos y reportes. La API no debe crear usuarios ni cambiar "
        "roles: es una operación de administrador fuera del alcance del asistente."
    ),
    "otros": "Sin agrupación definida; usa `describe_entity` para inspeccionarla.",
}

HEADER = '''"""Catálogo estático de las entidades de QMedic.

Generado por `scripts/generate_qmedic_catalog.py` a partir del metadata de QMedic
(`custom/Espo/Custom/Resources`). **No editar a mano**: se regenera.

El catálogo sirve para que el modelo descubra el vocabulario del proyecto sin
descargar el metadata completo; la instancia sigue siendo la autoridad, y
`describe_entity` consulta el metadata vivo cuando puede.
"""
from __future__ import annotations

from typing import Any
'''


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _label(name: str, scope_names: dict[str, str], i18n_dir: Path) -> str:
    """Etiqueta de la entidad: `scopeNames` y, si falta, el propio i18n del scope."""
    if name in scope_names:
        return scope_names[name]
    path = i18n_dir / f"{name}.json"
    if path.exists():
        labels = _read_json(path).get("labels") or {}
        for key in (name, name.replace("_", " ")):
            if key in labels:
                return labels[key]
    return name


def _required(fields: dict[str, Any]) -> list[str]:
    """Campos que la API exigirá al crear.

    Se descartan los de infraestructura y los que tienen `default`, porque el
    servidor los rellena: pedirlos sería un falso positivo.
    """
    result = []
    for name, definition in fields.items():
        if not isinstance(definition, dict) or not definition.get("required"):
            continue
        if name in BOILERPLATE_FIELDS or definition.get("readOnly"):
            continue
        if definition.get("default") is not None:
            continue
        result.append(name)
    return sorted(result)


def _enums(fields: dict[str, Any]) -> dict[str, list[str]]:
    """Opciones cerradas por campo, para validar antes de enviar.

    Se descartan las opciones que son identificadores de registro. QMedic tiene
    enums rellenados con IDs reales (`Contact.medicoReceptor`), y esos valores
    cambian con cada alta y no deberían quedar escritos en un archivo versionado.
    """
    result: dict[str, list[str]] = {}
    for name, definition in fields.items():
        if not isinstance(definition, dict):
            continue
        if definition.get("type") not in ("enum", "multiEnum"):
            continue
        options = definition.get("options")
        if not isinstance(options, list) or not options:
            continue
        if not all(isinstance(item, str) for item in options):
            continue
        cleaned = [item for item in options if not RECORD_ID_PATTERN.match(item)]
        if cleaned:
            result[name] = cleaned
    return result


def _datetimes(fields: dict[str, Any]) -> list[str]:
    """Campos que la instancia interpreta como fecha y hora (no solo fecha).

    7.5.6 acepta `YYYY-MM-DD HH:mm:ss` en UTC y nada más, así que conocer estos
    campos permite convertir la hora local antes de enviarla aunque el metadata no
    esté disponible. `createdAt`/`modifiedAt` quedan fuera: son de solo lectura.
    """
    return sorted(
        name
        for name, definition in fields.items()
        if isinstance(definition, dict)
        and not definition.get("readOnly")
        and name not in BOILERPLATE_FIELDS
        and str(definition.get("type", "")).startswith("datetime")
    )


def _links(links: dict[str, Any]) -> dict[str, str]:
    """Enlaces de dominio: nombre -> entidad destino (sin el ruido de EspoCRM)."""
    result: dict[str, str] = {}
    for name, definition in links.items():
        if name in BOILERPLATE_LINKS or not isinstance(definition, dict):
            continue
        target = definition.get("entity")
        if isinstance(target, str) and target:
            result[name] = target
    return result


def _group_of(entity: str, assigned: dict[str, str]) -> str:
    return assigned.get(entity, "otros")


def collect(metadata_root: Path) -> dict[str, Any]:
    entity_defs = metadata_root / "metadata" / "entityDefs"
    scopes_dir = metadata_root / "metadata" / "scopes"
    i18n_dir = metadata_root / "i18n" / "es_ES"
    if not entity_defs.is_dir():
        raise SystemExit(f"No encuentro entityDefs en {entity_defs}")

    global_i18n = i18n_dir / "Global.json"
    scope_names: dict[str, str] = {}
    if global_i18n.exists():
        scope_names = _read_json(global_i18n).get("scopeNames") or {}

    assigned = {
        entity: group for group, (_, members) in GROUPS.items() for entity in members
    }

    entities: dict[str, Any] = {}
    ungrouped: list[str] = []
    for path in sorted(entity_defs.glob("*.json")):
        name = path.stem
        definition = _read_json(path)
        scope = (
            _read_json(scopes_dir / f"{name}.json")
            if (scopes_dir / f"{name}.json").exists()
            else {}
        )
        if scope.get("entity") is False:
            # El scope existe pero declara que no hay entidad con API. Los scopes de
            # entidades del núcleo (Contact, Account…) suelen ser un override que no
            # repite `entity: true`, así que solo se descarta un `false` explícito.
            continue

        fields = definition.get("fields") or {}
        entry: dict[str, Any] = {
            "label": _label(name, scope_names, i18n_dir),
            "group": _group_of(name, assigned),
        }
        if "name" in fields:
            entry["name"] = "name"
        status_field = scope.get("statusField")
        if isinstance(status_field, str) and status_field:
            entry["status"] = status_field
        required = _required(fields)
        if required:
            entry["required"] = required
        enums = _enums(fields)
        if enums:
            entry["enums"] = enums
        datetimes = _datetimes(fields)
        if datetimes:
            entry["datetimes"] = datetimes
        links = _links(definition.get("links") or {})
        if links:
            entry["links"] = links
        if scope.get("stream"):
            entry["stream"] = True
        entities[name] = entry
        if entry["group"] == "otros":
            ungrouped.append(name)

    return {
        "entities": entities,
        "ungrouped": ungrouped,
        "groups": {key: text for key, (text, _) in GROUPS.items()},
        "workflow": WORKFLOW,
    }


def render(collected: dict[str, Any]) -> str:
    entities = collected["entities"]
    groups = collected["groups"]
    workflow = collected["workflow"]

    lines = [HEADER]
    lines.append("")
    lines.append("# En qué consiste cada grupo funcional.")
    lines.append("QMEDIC_GROUPS: dict[str, str] = {")
    for key, text in groups.items():
        lines.append(f"    {key!r}: (")
        lines.append(f"        {text!r}")
        lines.append("    ),")
    lines.append("    'otros': (")
    lines.append("        'Sin agrupación definida; usa `describe_entity` para inspeccionarla.'")
    lines.append("    ),")
    lines.append("}")
    lines.append("")
    lines.append("# Por dónde entrar en cada grupo, en una frase accionable.")
    lines.append("QMEDIC_WORKFLOW: dict[str, str] = {")
    for key, text in workflow.items():
        lines.append(f"    {key!r}: (")
        lines.append(f"        {text!r}")
        lines.append("    ),")
    lines.append("}")
    lines.append("")
    lines.append("# Entidad -> etiqueta de la interfaz, grupo, campos obligatorios,")
    lines.append("# opciones cerradas y enlaces de dominio. Lo ausente no existe en esta")
    lines.append("# instancia.")
    lines.append("QMEDIC_ENTITIES: dict[str, dict[str, Any]] = {")
    for name, entry in entities.items():
        lines.append(f"    {name!r}: {{")
        lines.append(f"        'label': {entry['label']!r},")
        lines.append(f"        'group': {entry['group']!r},")
        if "name" in entry:
            lines.append(f"        'name': {entry['name']!r},")
        if "status" in entry:
            lines.append(f"        'status': {entry['status']!r},")
        if entry.get("stream"):
            lines.append("        'stream': True,")
        if entry.get("required"):
            lines.append(f"        'required': {entry['required']!r},")
        if entry.get("datetimes"):
            lines.append(f"        'datetimes': {entry['datetimes']!r},")
        if entry.get("enums"):
            lines.append("        'enums': {")
            for field, options in entry["enums"].items():
                lines.append(f"            {field!r}: {options!r},")
            lines.append("        },")
        if entry.get("links"):
            lines.append("        'links': {")
            for link, target in entry["links"].items():
                lines.append(f"            {link!r}: {target!r},")
            lines.append("        },")
        lines.append("    },")
    lines.append("}")
    lines.append("")
    lines.append("")
    lines.append("def describe_catalog_entry(name: str) -> dict[str, Any] | None:")
    lines.append('    """La ficha del catálogo para `name`, o None si QMedic no la define."""')
    lines.append("    entry = QMEDIC_ENTITIES.get(name)")
    lines.append("    if entry is None:")
    lines.append("        return None")
    lines.append('    return {"entity": name, **entry, "source": "catalog"}')
    lines.append("")
    lines.append("")
    lines.append("def entities_in_group(group: str) -> list[str]:")
    lines.append('    """Nombres de entidad del grupo, ordenados."""')
    lines.append("    return sorted(")
    lines.append("        name for name, entry in QMEDIC_ENTITIES.items() if entry['group'] == group")
    lines.append("    )")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="No escribe: falla si el archivo versionado no coincide.",
    )
    args = parser.parse_args(argv)

    collected = collect(args.metadata)
    rendered = render(collected)

    if collected["ungrouped"]:
        print(
            "Aviso: entidades sin grupo: " + ", ".join(collected["ungrouped"]),
            file=sys.stderr,
        )

    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if current != rendered:
            print(
                f"{args.output.name} está desactualizado; vuelve a generarlo.",
                file=sys.stderr,
            )
            return 1
        print(f"{args.output.name} coincide con el metadata de QMedic.")
        return 0

    args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(
        f"{len(collected['entities'])} entidades escritas en {args.output}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
