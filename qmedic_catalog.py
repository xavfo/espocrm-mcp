"""Catálogo estático de las entidades de QMedic.

Generado por `scripts/generate_qmedic_catalog.py` a partir del metadata de QMedic
(`custom/Espo/Custom/Resources`). **No editar a mano**: se regenera.

El catálogo sirve para que el modelo descubra el vocabulario del proyecto sin
descargar el metadata completo; la instancia sigue siendo la autoridad, y
`describe_entity` consulta el metadata vivo cuando puede.
"""
from __future__ import annotations

from typing import Any


# En qué consiste cada grupo funcional.
QMEDIC_GROUPS: dict[str, str] = {
    'clinico': (
        'Atención de pacientes: historia, signos vitales, diagnósticos y órdenes.'
    ),
    'especialidad': (
        'Datos de una especialidad concreta (antropometría, oftalmología, odontología, salud mental, vacunas, obstetricia).'
    ),
    'recetas': (
        'Prescripciones y sus líneas: lo que el paciente debe tomar o aplicarse.'
    ),
    'facturacion': (
        'Facturación, cotizaciones, precios y pagos.'
    ),
    'inventario': (
        'Productos, proveedores, bodegas y movimientos de existencias.'
    ),
    'contabilidad': (
        'Contabilidad y tesorería.'
    ),
    'comercial': (
        'Cuentas, convenios y aseguradoras con las que se factura.'
    ),
    'comunicaciones': (
        'Mensajería de WhatsApp y llamadas.'
    ),
    'fhir': (
        'Motor de interoperabilidad FHIR y su configuración.'
    ),
    'actividad': (
        'Reuniones, llamadas, tareas y correos (núcleo de EspoCRM).'
    ),
    'administracion': (
        'Usuarios, equipos, personal y reportes.'
    ),
    'otros': (
        'Sin agrupación definida; usa `describe_entity` para inspeccionarla.'
    ),
}

# Por dónde entrar en cada grupo, en una frase accionable.
QMEDIC_WORKFLOW: dict[str, str] = {
    'clinico': (
        'La historia clínica cuelga de Contact, cuya etiqueta es «Paciente». Para atender un caso: busca el paciente por `pacienteCedula` o por nombre, lista su enlace `atenciones` y entra en la Atencion, que enlaza `signosVitales`, `procedimientos` y `protocoloCIAPs`. Las recetas no cuelgan de la Atencion: están en el enlace `recetas` del propio Contact.'
    ),
    'especialidad': (
        'Cada especialidad guarda sus mediciones en su propia entidad y las enlaza al paciente o a la consulta. Los rangos de referencia de antropometría están en Percentil y en las entidades de cada especialidad, no en las «Chart*», que son el plan de cuentas contable.'
    ),
    'recetas': (
        'Receta es la cabecera (enlaza `contact`, `meeting` e `idDiagnosticos`) y RecetaProducto la línea, con `producto` y `receta`. Prescription, Prscpackage y Prscdspnlineitem son un modelo de prescripción alterno: comprueba con `describe_entity` cuál usa la instancia antes de escribir.'
    ),
    'facturacion': (
        'Invoice es la factura y su enlace `items` las líneas; InvoiceItem lleva `taxTypes` y `transTaxDetails`. Quote/QuoteItem es la cotización. Los impuestos y las condiciones de pago se referencian por ID, así que lista TaxGroups y PaymentTerms antes de crear una factura.'
    ),
    'inventario': (
        'Product es el artículo; Product.precios enlaza Precio y StockMoves registra cada movimiento con `product` y `location`, mientras LocStock guarda el saldo por bodega. No escribas StockMoves sin un motivo de movimiento válido.'
    ),
    'contabilidad': (
        'El plan de cuentas es ChartClass -> ChartTypes -> ChartMaster. Asientos es el asiento y GlTrans sus líneas; LibroDiario y LibroMayor son los libros. Estas entidades suelen ser de solo lectura para un usuario de API.'
    ),
    'comercial': (
        'Account es la cuenta de facturación y el paciente la referencia con `cuentaFacturacion`; el paciente es Contact, nunca Account. Convenio, Contrato, Prestador y MedicinaPrepagada formalizan la tarifa.'
    ),
    'comunicaciones': (
        'Wischat/GruposWhatsapp configuran la mensajería; MensajeWhastappMasivo registra los envíos masivos. Enviar mensajes reales tiene efecto externo: confirma con el usuario antes de crear un envío.'
    ),
    'fhir': (
        'Estas entidades configuran el mapeo FHIR. Leer está bien; escribir puede romper la interoperabilidad, así que pide confirmación explícita.'
    ),
    'actividad': (
        'Meeting es la consulta (su etiqueta en QMedic es «Consulta»), junto con Call y Task. Se asignan al usuario de la API cuando no se indica otro (ESPO_AUTO_ASSIGN) y pueden colgar de un paciente con `parent`.'
    ),
    'administracion': (
        'Usuarios, equipos y reportes. La API no debe crear usuarios ni cambiar roles: es una operación de administrador fuera del alcance del asistente.'
    ),
    'otros': (
        'Sin agrupación definida; usa `describe_entity` para inspeccionarla.'
    ),
}

# Entidad -> etiqueta de la interfaz, grupo, campos obligatorios,
# opciones cerradas y enlaces de dominio. Lo ausente no existe en esta
# instancia.
QMEDIC_ENTITIES: dict[str, dict[str, Any]] = {
    'Account': {
        'label': 'Cuenta (facturación)',
        'group': 'comercial',
        'stream': True,
        'enums': {
            'tipoIdentificacion': ['04', '05', '06', '07', '08'],
        },
        'links': {
            'paciente': 'Contact',
            'consulta': 'Meeting',
            'salesType': 'SalesType',
            'prestador': 'User',
            'planes': 'Plan',
            'usuario': 'User',
        },
    },
    'Actividad': {
        'label': 'Actividad Diaria',
        'group': 'clinico',
        'name': 'name',
        'status': 'status',
        'required': ['dateEnd', 'name'],
        'datetimes': ['dateEnd', 'dateStart'],
        'enums': {
            'status': ['Planned', 'Held', 'Not Held'],
            'tipo': ['DESPERTARSE', 'DESAYUNO', 'ALMUERZO', 'CENA', 'DORMIR'],
            'hora': ['00H00', '00H30', '01H00', '01H30', '02H00', '02H30', '03H00', '03H30', '04H00', '04H30', '05H00', '05H30', '06H00', '06H30', '07H00', '07H30', '08H00', '08H30', '09H00', '09H30', '10H00', '10H30', '11H00', '11H30', '12H00', '12H30', '13H00', '13H30', '14H00', '14H30', '15H00', '15H30', '16H00', '16H30', '17H00', '17H30', '18H00', '18H30', '19H00', '19H30', '20H00', '20H30', '21H00', '21H30', '22H00', '22H30', '23H00', '23H30'],
        },
        'links': {
            'paciente': 'Contact',
        },
    },
    'AgudezaVisual': {
        'label': 'Optometría',
        'group': 'especialidad',
        'name': 'name',
        'stream': True,
        'links': {
            'profesional': 'User',
            'paciente': 'Contact',
            'ordenesDeTrabajo': 'OrdenDeTrabajo',
        },
    },
    'Anticonceptivo': {
        'label': 'Anticonceptivo',
        'group': 'especialidad',
        'name': 'name',
        'enums': {
            'tipo': ['Implante subdérmico', 'Dispositivo intrauterino', 'Métodos anticonceptivos hormonales', 'Métodos anticonceptivos de barrera', 'Ciclo menstrual', 'Anticonceptivos de emergencia '],
        },
        'links': {
            'paciente': 'Contact',
        },
    },
    'Area': {
        'label': 'Area',
        'group': 'comercial',
        'name': 'name',
        'required': ['name'],
        'links': {
            'custBranchs': 'CustBranch',
            'contact': 'Contact',
        },
    },
    'Asientos': {
        'label': 'Asientos',
        'group': 'contabilidad',
        'name': 'name',
        'required': ['name'],
        'enums': {
            'cuenta': ['Bancos', 'Cuentas por cobrar', 'Ingreso Ventas', 'IVA Ventas', 'IRF Retenido', 'IVA Retenido'],
        },
        'links': {
            'libroMayor': 'LibroMayor',
            'cuentasCategorias': 'CuentasCategoria',
        },
    },
    'Atencion': {
        'label': 'Atención',
        'group': 'clinico',
        'name': 'name',
        'status': 'estado',
        'stream': True,
        'datetimes': ['eventoFechaHora', 'fechaIngreso', 'fechaSalida'],
        'enums': {
            'estado': ['Inicial', 'Triage', 'Observación', 'Internamiento', 'Tratamiento', 'Tratamiento Ambulatorio', 'Alta'],
            'triage': ['0', '1', '2', '3', '4', '5'],
            'medioDeIngreso': ['Ambulatorio', 'Ambulancia', 'Otro transporte'],
            'motivoDeAtencion': ['Trauma', 'Causa Clínica', 'Causa G. Obstétrica', 'Causa Quirúrgica', 'Notificación Policial', 'Accidente, violencia, intoxicación, envenenamiento o quemadura', 'Otro Motivo'],
        },
        'links': {
            'protocoloCIAPs': 'ProtocoloCIAP',
            'paciente': 'Contact',
            'noPaciente': 'Lead',
            'procedimientos': 'Product',
            'signosVitales': 'SignosVitales',
        },
    },
    'BranchOffice': {
        'label': 'Branch Office',
        'group': 'comercial',
        'name': 'name',
        'links': {
            'salesOrders': 'SalesOrders',
            'debtorTrans': 'DebtorTrans',
            'empresa': 'Company',
            'oficinas': 'Oficina',
        },
    },
    'Call': {
        'label': 'Call',
        'group': 'actividad',
    },
    'Campaign': {
        'label': 'Campaign',
        'group': 'comercial',
        'links': {
            'mensajesWhastappMasivos': 'MensajeWhastappMasivo',
        },
    },
    'Case': {
        'label': 'Ticket de Soporte',
        'group': 'comercial',
        'name': 'name',
        'status': 'status',
        'stream': True,
        'required': ['priority', 'status', 'type'],
        'enums': {
            'scope': ['Agreement', 'Bills', 'Charges', 'Claims', 'Collection', 'Communication', 'Profile', 'Document', 'Finance', 'Invoice', 'IT Apps', 'Member', 'Corporate', 'Courier', 'Network', 'Payment', 'Reports', 'Staff', 'Statement', 'Prescription'],
            'severity': ['High', 'Medium', 'Low', 'Disaster'],
        },
        'links': {
            'member': 'Member',
            'courier': 'Courier',
            'caseParent': 'Case',
            'cases': 'Case',
            'prescription': 'Prescription',
            'plan': 'Plan',
            'contrato': 'Contrato',
        },
    },
    'Categoria': {
        'label': 'Categoria',
        'group': 'clinico',
        'name': 'name',
        'required': ['name'],
        'links': {
            'idDiagnosticos': 'IdDiagnostico',
            'users': 'User',
        },
    },
    'Certificado': {
        'label': 'Certificado',
        'group': 'clinico',
        'name': 'name',
        'required': ['certificadoPaciente'],
        'datetimes': ['asistenciaFechaDesde', 'asistenciaFechaHasta'],
        'enums': {
            'certificadoContril': ['1', '2', '3', '4', '5', '10', '15', '20', '25', '30', '35', '40', '45', '60', '90', ''],
            'tipo': ['Asistencia', 'Reposo', 'Resumen de Historia'],
            'tipoDeContingencia': ['MATERNIDAD', 'ENFERMEDAD CATASTRÓFICA', 'ENFERMEDAD GENERAL'],
            'accion': ['...', 'Enviar a Paciente'],
            'estado': ['Vigente', 'No vigente', 'Anulado'],
            'asistencia': ['Presencial', 'Virtual', 'Visita a domicilio'],
        },
        'links': {
            'certificadoUsuario': 'User',
            'certificadoPaciente': 'Contact',
            'certificadoDiagnostico': 'IdDiagnostico',
            'idDiagnosticos': 'IdDiagnostico',
            'wischats': 'Wischat',
        },
    },
    'ChartClass': {
        'label': 'Clase de Cuentas Contables',
        'group': 'contabilidad',
        'name': 'name',
        'required': ['name'],
        'enums': {
            'ctype': ['1', '2', '3', '4', '5', '6'],
        },
        'links': {
            'chartTypeses': 'ChartTypes',
        },
    },
    'ChartMaster': {
        'label': 'Cuenta Contable',
        'group': 'contabilidad',
        'name': 'name',
        'required': ['name'],
        'enums': {
            'estado': ['G', 'M'],
        },
        'links': {
            'chartTypes': 'ChartTypes',
            'taxTypesPurchasing': 'TaxTypes',
            'taxTypesSales': 'TaxTypes',
            'products': 'Product',
            'products1': 'Product',
            'products2': 'Product',
            'products3': 'Product',
            'products4': 'Product',
            'custBranchs': 'CustBranch',
            'custBranchs1': 'CustBranch',
            'custBranchs12': 'CustBranch',
            'custBranchs123': 'CustBranch',
            'contact': 'Contact',
            'contact1': 'Contact',
            'contact12': 'Contact',
            'contact123': 'Contact',
        },
    },
    'ChartTypes': {
        'label': 'Tipo de Cuenta',
        'group': 'contabilidad',
        'name': 'name',
        'required': ['name'],
        'links': {
            'chartTypeses': 'ChartTypes',
            'chartTypesParent': 'ChartTypes',
            'chartClas': 'ChartClass',
            'chartMasters': 'ChartMaster',
        },
    },
    'Company': {
        'label': 'Empresa / Matriz',
        'group': 'comercial',
        'name': 'name',
        'enums': {
            'obligadoALlevarContabilidad': ['SI', 'NO'],
            'regimenRimpe': ['', 'CONTRIBUYENTE RÉGIMEN RIMPE', 'CONTRIBUYENTE NEGOCIO POPULAR - RÉGIMEN RIMPE'],
        },
        'links': {
            'profesionales': 'User',
            'oficinas': 'Oficina',
            'salesPoints': 'SalesPoint',
            'branchOffices': 'BranchOffice',
            'libroDiarios': 'LibroDiario',
        },
    },
    'Compra': {
        'label': 'Compra',
        'group': 'inventario',
        'name': 'name',
        'required': ['name'],
    },
    'Condicion': {
        'label': 'Condicion',
        'group': 'clinico',
        'name': 'name',
        'datetimes': ['abatementDateTime', 'assertedDate'],
        'enums': {
            'clinicalStatus': ['active', 'recurrence', 'inactive', 'remission', 'resolved'],
            'verificationStatus': ['provisional', 'differential', 'confirmed', 'refuted', 'entered-in-error', 'unknown'],
        },
        'links': {
            'paciente': 'Contact',
            'evidencesupport': 'Attachment',
            'idDiagnosticos': 'IdDiagnostico',
        },
    },
    'Consentimiento': {
        'label': 'Consentimiento',
        'group': 'clinico',
        'name': 'name',
        'datetimes': ['consentimientoEmision'],
        'enums': {
            'consObjetivo': ['CIRUGlA COMO TRATAMIENTO DE INFERTILIDAD', 'MIOMECTOMÍA', 'LEGRADO', 'LAPAROTOMÍA EXPLORADORA', 'INSEMINACIÓN ARTIFICIAL', 'INDUCCIÓN DE OVULACIÓN', 'INDUCCIÓN DEL PARTO', 'CIRUGÍA DE INCONTINENCIA URINARIA', 'HISTERECTOMÍA', 'CONTROL PRENATAL', 'CONSULTA Y ESTUDIO  DE INFERTILIDAD', 'CIRUGÍA DE CÉRVIX', 'CIRUGÍA LAPAROSCÓPICA', 'OPERACIÓN CESÁREA', 'CERCLAJE', 'CONSULTA GINECOLÓGICA', 'CONSULTA PSIQUIÁTRICA', 'CONSULTA PSICOLÓGICA', 'CIRUGÍA DE OCLUSIÓN TUBÁRICA', 'RESECCIÓN DE MASA EN SENO', 'REMISIÓN', 'CIRUGÍA', 'CONSULTA MÉDICA', 'FORMA 024'],
        },
        'links': {
            'consentimientoArchivos': 'Attachment',
            'consentimientoOficina': 'Oficina',
            'motivos': 'ConsentimientoMotivo',
            'consentimientoProfesional': 'User',
            'consentimientoPaciente': 'Contact',
        },
    },
    'ConsentimientoMotivo': {
        'label': 'Motivo Consentimiento',
        'group': 'clinico',
        'name': 'name',
        'stream': True,
        'required': ['name'],
        'links': {
            'consentimiento': 'Consentimiento',
        },
    },
    'Contact': {
        'label': 'Paciente',
        'group': 'clinico',
        'stream': True,
        'required': ['lastName', 'pacienteCedula'],
        'enums': {
            'pacienteANutricionales': ['Obesidad', 'Diabetes', 'HTA', 'Cáncer', 'Hipercolesterolemia', 'Hipertrigliceridemia'],
            'estado': ['Activo', 'Inactivo', 'Archivado', 'Alta por Abandono'],
            'acciones': ['Copiar datos de facturación', ''],
            'tipoSanguineo': ['A +', 'A -', 'B +', 'B -', 'O +', 'O -', 'AB +', 'AB -', 'no tipificado'],
            'pacienteHabitosDeSalud': ['Tabaquismo', 'Alcoholismo', 'Drogas', 'Actividad Física', 'Automedicación', 'Pasatiempos', 'Gimnasio'],
            'pacientePartoTrabajo': ['Inducido', 'Espontáneo', 'Complicaciones'],
            'idTipo': ['Cédula', 'Pasaporte'],
            'referenciaDePacientes': ['...', 'Interconsulta', 'Derivación'],
            'medicoReceptor': ['Seleccione para direccionar'],
            'relacion': ['Otros', 'Auxiliar', 'Familiar', 'Vecino'],
        },
        'links': {
            'recetas': 'Receta',
            'pedidos': 'Pedido',
            'actividad': 'Task',
            'pesoTallas': 'PesoTalla',
            'signosVitales': 'SignosVitales',
            'resultados': 'Resultados',
            'pacienteSeguro': 'MedicinaPrepagada',
            'controlTractoGenital': 'TractoGenital',
            'examenesPsiquiatricos': 'ExamenPsiquiatrico',
            'wischats': 'Wischat',
            'condiciones': 'Condicion',
            'consentimiento': 'Consentimiento',
            'iMCs': 'IMC',
            'inmunizaciones': 'Inmunizacin',
            'anticonceptivos': 'Anticonceptivo',
            'nutricion': 'Nutricion',
            'actividades': 'Actividad',
            'certificados': 'Certificado',
            'edadGestacional': 'Fum',
            'fisicos': 'Fisico',
            'odontograma': 'Odontograma',
            'atenciones': 'Atencion',
            'custBranch': 'CustBranch',
            'cuentaFacturacion': 'Account',
            'pruebaSicologica': 'PruebaSicolgica',
            'respuestasPruebaS': 'RespuestaPruebaS',
            'sesiones': 'Sesion',
            'fhirMap': 'FhirMap',
            'registrosAgudezaVisual': 'AgudezaVisual',
            'recetaOftalmologicas': 'RecetaOftalmologica',
            'ordenesDeTrabajo': 'OrdenDeTrabajo',
            'perfil': 'Attachment',
            'responsable': 'Lead',
            'contratos': 'Contrato',
        },
    },
    'Contrato': {
        'label': 'Contrato',
        'group': 'comercial',
        'name': 'name',
        'stream': True,
        'required': ['name'],
        'enums': {
            'estado': ['Contratado', 'Carencia', 'Activo', 'Suspendido', 'Cancelado'],
            'tipo': ['Individual', 'Colectivo'],
        },
        'links': {
            'planes': 'Plan',
            'usuario': 'User',
            'pagador': 'Lead',
            'beneficiario': 'Contact',
            'casos': 'Case',
        },
    },
    'Convenio': {
        'label': 'Convenio',
        'group': 'comercial',
        'name': 'name',
        'required': ['name'],
        'enums': {
            'estado': ['Activo', 'Inactivo'],
        },
        'links': {
            'planes': 'Plan',
            'tarifarios': 'Tarifario',
            'prestador': 'Prestador',
        },
    },
    'Courier': {
        'label': 'Courier',
        'group': 'inventario',
        'name': 'name',
        'stream': True,
        'required': ['name'],
        'enums': {
            'branchType': ['Main', 'Branch', 'Subsidiary', 'Associate', 'Franchise'],
            'bankCode': ['00', '32', '49', '12', '53', '8', '45', '7', '52', '2', '10', '35', '17', '19', '23', '24', '22', '48', '47', '27', '41', '29', '33', '18', '14', '51', '46', '26', '4', '60', '59', '73'],
            'paymentVia': ['Cheque', 'Cash', 'Account'],
            'accountStatus': ['Active', 'Deactivated', 'Closed'],
        },
        'links': {
            'courierParent': 'Courier',
            'couriers': 'Courier',
            'cases': 'Case',
            'prscpackages': 'Prscpackage',
            'contacts': 'Contact',
            'cotizaciones': 'Quote',
        },
    },
    'CreditStatus': {
        'label': 'Estado Crediticio',
        'group': 'facturacion',
        'name': 'name',
        'required': ['name'],
        'links': {
            'contacts': 'Contact',
        },
    },
    'CuentaBancaria': {
        'label': 'Cuenta Bancaria',
        'group': 'contabilidad',
        'name': 'name',
        'required': ['name'],
    },
    'CuentaEmpresa': {
        'label': 'CuentaEmpresa',
        'group': 'contabilidad',
        'name': 'name',
        'stream': True,
        'required': ['name'],
    },
    'Cuentas': {
        'label': 'Cuenta Contable II',
        'group': 'contabilidad',
        'name': 'name',
        'required': ['name'],
        'links': {
            'cuentaUsuario': 'User',
            'cuentasCategoria': 'CuentasCategoria',
            'cotizacion': 'Quote',
            'plan': 'Plan',
        },
    },
    'CuentasCategoria': {
        'label': 'Categoría de Cuenta',
        'group': 'contabilidad',
        'name': 'name',
        'required': ['name'],
        'links': {
            'cuentas': 'Cuentas',
            'asientos': 'Asientos',
        },
    },
    'CustBranch': {
        'label': 'Información de Facturación',
        'group': 'comercial',
        'name': 'name',
        'enums': {
            'salutationName': ['', 'Mr.', 'Ms.', 'Mrs.', 'Dr.'],
        },
        'links': {
            'area': 'Area',
            'salesman': 'User',
            'location': 'Location',
            'salesAccount': 'ChartMaster',
            'salesDiscountAccount': 'ChartMaster',
            'receivablesAccount': 'ChartMaster',
            'paymentDiscountAccount': 'ChartMaster',
            'shippingProvider': 'ShippingProvider',
            'salesGroup': 'SalesGroup',
            'contact1': 'Contact',
            'contact': 'Contact',
            'usuario': 'User',
        },
    },
    'DebtorTrans': {
        'label': 'Factura Debtor',
        'group': 'facturacion',
        'name': 'name',
        'stream': True,
        'enums': {
            'salutationName': ['', 'Mr.', 'Ms.', 'Mrs.', 'Dr.'],
            'type': ['10', '11', '13', '12'],
            'accion1': ['Borrador', 'Enviar a SRI', 'Factura Enviada'],
        },
        'links': {
            'contact': 'Contact',
            'debtorTransDetails': 'DebtorTransDetails',
            'location': 'Location',
            'shippingProvider': 'ShippingProvider',
            'salesOrders': 'SalesOrders',
            'salesPoint': 'SalesPoint',
            'oficinas': 'Oficina',
        },
    },
    'DebtorTransDetails': {
        'label': 'Detalle de Factura',
        'group': 'facturacion',
        'name': 'name',
        'required': ['name'],
        'links': {
            'debtorTrans': 'DebtorTrans',
            'transTaxDetails': 'TransTaxDetails',
            'product': 'Product',
            'product1': 'Product',
        },
    },
    'Diente': {
        'label': 'Diente',
        'group': 'especialidad',
        'name': 'name',
        'stream': True,
        'enums': {
            'tipo': ['Diente', 'Muela', 'Deciduo'],
        },
        'links': {
            'odontograma': 'Odontograma',
            'imagen': 'Attachment',
            'procedimientos': 'Procedimiento',
            'tratamientoOdontologicos': 'TratamientoOdontologico',
            'imagenes': 'Attachment',
        },
    },
    'Dimensions': {
        'label': 'Dimensions',
        'group': 'contabilidad',
        'name': 'name',
        'required': ['name'],
    },
    'DocElectronicos': {
        'label': 'DocElectronicos',
        'group': 'facturacion',
        'name': 'name',
        'stream': True,
        'required': ['name'],
    },
    'Document': {
        'label': 'Document',
        'group': 'actividad',
    },
    'Email': {
        'label': 'Email',
        'group': 'actividad',
    },
    'Empleado': {
        'label': 'Empleado',
        'group': 'administracion',
        'name': 'name',
        'required': ['name'],
    },
    'EmpresaMedicinaPrepagada': {
        'label': 'EmpresaMedicinaPrepagada',
        'group': 'comercial',
        'name': 'name',
        'required': ['name'],
        'datetimes': ['fechaSC'],
        'links': {
            'planMedicinaPrepagadas': 'MedicinaPrepagada',
        },
    },
    'ExamenPsiquiatrico': {
        'label': 'Examen Psiquiátrico',
        'group': 'especialidad',
        'name': 'name',
        'links': {
            'paciente': 'Contact',
        },
    },
    'FacturacionSecuencial': {
        'label': 'FacturacionSecuencial',
        'group': 'facturacion',
        'name': 'name',
        'enums': {
            'tipoDeDocumento': ['Factura', 'Nota de Credito', 'Nota de Debito', 'Retencion', 'Guia de Remision'],
        },
    },
    'FhirConst': {
        'label': 'FhirConst',
        'group': 'fhir',
        'name': 'name',
        'required': ['name'],
        'links': {
            'fhirMaps': 'FhirMap',
        },
    },
    'FhirDependent': {
        'label': 'FhirDependent',
        'group': 'fhir',
        'name': 'name',
        'required': ['name'],
        'links': {
            'fhirRules': 'FhirRule',
            'fhirParameter': 'FhirParameter',
        },
    },
    'FhirGroup': {
        'label': 'FhirGroup',
        'group': 'fhir',
        'name': 'name',
        'required': ['name'],
        'links': {
            'fhirMaps': 'FhirMap',
            'fhirInput': 'FhirInput',
            'fhirRule': 'FhirRule',
        },
    },
    'FhirInput': {
        'label': 'FhirInput',
        'group': 'fhir',
        'name': 'name',
        'required': ['name'],
        'links': {
            'fhirGroups': 'FhirGroup',
        },
    },
    'FhirMap': {
        'label': 'FHIR Structure Map',
        'group': 'fhir',
        'name': 'name',
        'required': ['name', 'url'],
        'enums': {
            'status': ['draft', 'active', 'retired', 'unknown'],
        },
        'links': {
            'fhirStructure': 'FhirStructure',
            'fhirConst': 'FhirConst',
            'fhirGroup': 'FhirGroup',
            'paciente': 'Contact',
        },
    },
    'FhirParameter': {
        'label': 'FhirParameter',
        'group': 'fhir',
        'name': 'name',
        'required': ['name'],
        'links': {
            'fhirTargets': 'FhirTarget',
            'fhirDependents': 'FhirDependent',
        },
    },
    'FhirRule': {
        'label': 'FhirRule',
        'group': 'fhir',
        'name': 'name',
        'required': ['name'],
        'links': {
            'fhirGroups': 'FhirGroup',
            'fhirTarget': 'FhirTarget',
            'fhirRules': 'FhirRule',
            'fhirRuleParent': 'FhirRule',
            'fhirSource': 'FhirSource',
            'fhirDependent': 'FhirDependent',
        },
    },
    'FhirSource': {
        'label': 'FhirSource',
        'group': 'fhir',
        'name': 'name',
        'required': ['name'],
        'links': {
            'fhirRules': 'FhirRule',
        },
    },
    'FhirStructure': {
        'label': 'FhirStructure',
        'group': 'fhir',
        'name': 'name',
        'stream': True,
        'required': ['name'],
        'links': {
            'fhirMaps': 'FhirMap',
        },
    },
    'FhirTarget': {
        'label': 'FhirTarget',
        'group': 'fhir',
        'name': 'name',
        'required': ['name'],
        'links': {
            'fhirRules': 'FhirRule',
            'fhirParameter': 'FhirParameter',
        },
    },
    'FichaPrueba': {
        'label': 'Ficha Técnica de Prueba',
        'group': 'especialidad',
        'name': 'name',
        'stream': True,
        'required': ['name'],
        'enums': {
            'estado': ['Activo', 'No activo'],
        },
        'links': {
            'pruebaSicologicas': 'PruebaSicolgica',
            'preguntasPruebaSicologica': 'PreguntaPruebaS',
            'respuestasPruebaS': 'RespuestaPruebaS',
            'materialDeApoyo': 'Attachment',
        },
    },
    'FiscalYear': {
        'label': 'Año Fiscal',
        'group': 'contabilidad',
        'name': 'name',
    },
    'Fisico': {
        'label': 'Exploración Física',
        'group': 'especialidad',
        'name': 'name',
        'links': {
            'paciente': 'Contact',
            'facial': 'Attachment',
            'corporal': 'Attachment',
            'consulta': 'Meeting',
            'imagenesExploracion': 'Attachment',
        },
    },
    'Fum': {
        'label': 'Fum',
        'group': 'especialidad',
        'name': 'name',
        'stream': True,
        'enums': {
            'accion1': ['Calcular', '.'],
        },
        'links': {
            'paciente': 'Contact',
        },
    },
    'GlTrans': {
        'label': 'GlTrans',
        'group': 'contabilidad',
        'name': 'name',
        'required': ['name'],
    },
    'GruposWhatsapp': {
        'label': 'Grupos de Whatsapp',
        'group': 'comunicaciones',
    },
    'IdDiagnostico': {
        'label': 'Diagnóstico',
        'group': 'clinico',
        'name': 'name',
        'stream': True,
        'required': ['name'],
        'links': {
            'meeting': 'Meeting',
            'categoria': 'Categoria',
            'recetas': 'Receta',
            'condicion': 'Condicion',
            'certificados': 'Certificado',
            'certificados1': 'Certificado',
            'protocoloCIAP': 'ProtocoloCIAP',
            'recetaOftalmologicaOI': 'RecetaOftalmologica',
            'recetaOftalmologicaOD': 'RecetaOftalmologica',
        },
    },
    'IMC': {
        'label': 'IMC',
        'group': 'especialidad',
        'name': 'name',
        'stream': True,
        'required': ['paciente'],
        'enums': {
            'accion1': ['Calcular'],
        },
        'links': {
            'paciente': 'Contact',
        },
    },
    'Inmunizacin': {
        'label': 'Inmunizacin',
        'group': 'especialidad',
        'name': 'name',
        'stream': True,
        'required': ['expiration', 'lote', 'name'],
        'datetimes': ['fecha'],
        'enums': {
            'status': ['completed', 'entered-in-error'],
            'route': ['IM', 'PO', 'NASINHL'],
        },
        'links': {
            'vacuna': 'Vacuna',
            'registro': 'Attachment',
            'paciente': 'Contact',
        },
    },
    'Interaccion': {
        'label': 'Interacción',
        'group': 'clinico',
        'name': 'name',
        'stream': True,
        'required': ['name'],
    },
    'Invoice': {
        'label': 'Factura',
        'group': 'facturacion',
        'name': 'name',
        'status': 'status',
        'stream': True,
        'datetimes': ['deliveryDate'],
        'enums': {
            'tipoDeAmbiente': ['1', '2'],
            'accion': ['Borrador', 'Enviar a SRI', 'Factura Enviada'],
            'type': ['10', '11', '12', '13'],
            'methodOfPayment': ['01', '15', '16', '17', '18', '19', '20', '21'],
        },
        'links': {
            'oficina': 'Oficina',
            'bodega': 'Location',
            'sucursales': 'Oficina',
            'shippingProvider1': 'ShippingProvider',
            'salesPoint': 'SalesPoint',
            'ubicacionActivosFijos': 'UbicacionActivosFijos',
        },
    },
    'InvoiceItem': {
        'label': 'InvoiceItem',
        'group': 'facturacion',
        'links': {
            'transTaxDetails': 'TransTaxDetails',
            'taxTypes': 'TaxTypes',
        },
    },
    'ItemUnits': {
        'label': 'ItemUnits',
        'group': 'inventario',
        'name': 'name',
        'required': ['name'],
        'links': {
            'products': 'Product',
        },
    },
    'Lead': {
        'label': 'No Paciente',
        'group': 'comercial',
        'status': 'status',
        'stream': True,
        'enums': {
            'tipoIdentificacion': ['RUC', 'Cédula', 'Pasaporte'],
        },
        'links': {
            'atenciones': 'Atencion',
            'paciente': 'Contact',
            'contratos': 'Contrato',
        },
    },
    'LibroDiario': {
        'label': 'LibroDiario',
        'group': 'contabilidad',
        'name': 'name',
        'stream': True,
        'enums': {
            'acciones': ['...', 'Cerrar día', 'Eliminar Cierre'],
        },
        'links': {
            'empresa': 'Company',
            'oficina': 'Oficina',
        },
    },
    'LibroMayor': {
        'label': 'LibroMayor',
        'group': 'contabilidad',
        'name': 'name',
        'stream': True,
        'required': ['name'],
        'links': {
            'asientos': 'Asientos',
        },
    },
    'Location': {
        'label': 'Bodega',
        'group': 'inventario',
        'name': 'name',
        'links': {
            'locStocks': 'LocStock',
            'stockMoves': 'StockMoves',
            'salesOrders': 'SalesOrders',
            'custBranchs': 'CustBranch',
            'contact': 'Contact',
            'debtorTrans': 'DebtorTrans',
            'facturas': 'Invoice',
        },
    },
    'LocStock': {
        'label': 'LocStock',
        'group': 'inventario',
        'name': 'name',
        'links': {
            'location': 'Location',
            'product': 'Product',
        },
    },
    'Medicationlist': {
        'label': 'Lista de Medicación',
        'group': 'especialidad',
        'name': 'name',
        'stream': True,
        'required': ['name', 'productCode'],
        'enums': {
            'medicationStatus': ['Discontinued', 'Stockout', 'Available', 'Banned'],
            'tipoFabricante': ['Nacional', 'Extranjero'],
        },
        'links': {
            'medicationImage': 'Attachment',
            'lineitems': 'Prscdspnlineitem',
            'marca': 'ProductBrand',
        },
    },
    'MedicinaPrepagada': {
        'label': 'Plan de Medicina Prepagada',
        'group': 'comercial',
        'name': 'name',
        'status': 'accion',
        'datetimes': ['fechaActivo', 'fechaFin'],
        'enums': {
            'accion': ['Por confirmar', 'No autorizado', 'Autorizado'],
        },
        'links': {
            'paciente': 'Contact',
            'empresaMedicinaPrepagada': 'EmpresaMedicinaPrepagada',
        },
    },
    'Meeting': {
        'label': 'Consulta',
        'group': 'actividad',
        'name': 'name',
        'status': 'status',
        'enums': {
            'consultaTipo': ['presencial', 'tele', 'domicilio'],
            'acciones': ['---', 'Crear Cotización'],
            'escalaDeDolor': ['0', '1-3', '4-6', '7-9', '10'],
            'tipoDeConsulta': ['Control', 'Primera consulta'],
        },
        'links': {
            'diagnosticos': 'IdDiagnostico',
            'grabacion': 'Attachment',
            'receta': 'Receta',
            'productos': 'Product',
            'consultaAdjuntos': 'Attachment',
            'wischats': 'Wischat',
            'pagos': 'Pago',
            'cotizaciones': 'Quote',
            'cuenta': 'Account',
            'fisico': 'Fisico',
            'ciclo': 'Sesion',
            'agendamiento': 'Task',
        },
    },
    'Member': {
        'label': 'Member',
        'group': 'administracion',
        'name': 'name',
        'stream': True,
        'required': ['dateofbirth', 'idnumber'],
        'enums': {
            'salutationName': ['', 'Mr.', 'Ms.', 'Mrs.', 'Dr.', 'Cik.', 'Che.', 'Puan', 'Tuan', 'Haji', "Dato'", 'Datuk', 'Tan Sri', 'Tun Dr.', 'Ir.'],
            'idtype': ['MyKad', 'Passport', 'DriverLicense', 'ArmyID', 'ForiegnID', 'SSNumber', 'UNCard'],
            'gender': ['Male', 'Female', 'Other'],
            'religion': ['Islam', 'Christianity', 'Hinduism', 'Buddhism', 'Chinese', 'Others', 'Atheist'],
            'race': ['Malay', 'Chinese', 'Indian', 'Others', 'Rohingya', 'Thai', 'Loatian', 'Vietnamese', 'Philippina', 'Bangladeshi', 'Pakistani', 'Myanmar', 'Arab', 'Kadazan-Dusun', 'Melanau', 'Iban', 'Bidayu', 'Not Known'],
            'commlanguage': ['Bahasa MY', 'Bahasa IN', 'Mandrin', 'Tamil', 'Hindi', 'Arabic', 'English', 'French', 'Spanish', 'Russian Bloc', 'Italian', 'German', 'Korean', 'Japanese', 'Burmese', 'Thai', 'Taglog', 'Vietnamese', 'Mynamar'],
            'nationality': ['Malaysia', 'Thailand', 'Mynmar', 'Singapore', 'Indonesia', 'India', 'Philippines', 'Bangladesh', 'Pakistan', 'Midde East Bloc', 'Russian Bloc'],
            'specialstatus': ['VIP', 'VVIP', 'Royalty', 'Exec', 'Normal'],
            'status': ['Active', 'Inactive', 'Suspended', 'Closed', 'Blocked'],
            'residencystatus': ['Citizen', 'Permanent Resident', 'Non-Resident', 'Refugee', 'Diplomat'],
            'paymentmode': ['Self', 'TPA', 'Emp'],
        },
        'links': {
            'subscriptionplans': 'Subscriptionplan',
            'account': 'Account',
            'cases': 'Case',
            'prscpackages': 'Prscpackage',
            'prescriptions': 'Prescription',
        },
    },
    'MensajeWhastappMasivo': {
        'label': 'MensajeWhastappMasivo',
        'group': 'comunicaciones',
        'name': 'name',
        'stream': True,
        'datetimes': ['iniciar'],
        'enums': {
            'estado': ['Pendiente'],
        },
        'links': {
            'campaign': 'Campaign',
        },
    },
    'Nutricion': {
        'label': 'Nutricion',
        'group': 'especialidad',
        'name': 'name',
        'enums': {
            'cantidadDeActividad': ['Muy ligera', 'Ligera', 'Moderada', 'Pesada', 'Excepcional'],
            'consumoDeDrogasSuaves': ['Alcohol - 120 ml/d', 'Alcohol - 350 ml/d', 'Alcohol - 45 ml/d', 'Alcohol <10° - 120 ml/d', 'Alcohol >10° <25° - 120 ml/d', 'Alcohol >50° - 120 ml/d', 'Alcohol <10° - 350 ml/d', 'Alcohol >10° <25° - 45 ml/d', 'Tabaco', 'Tabaco < 5 cigarillos / día', 'Tabaco - 6 a 15 cigarillos / día', 'Tabaco > 15 cigarillos / día', 'Café', 'Café - < 4 tazas / día', 'Café - de 5 a 8 tazas / día', 'Café - > 8 tazas / día'],
            'preparacionDeAlimentos': ['Madre/Padre', 'Pareja', 'Hijos', 'Uno mismo', 'Otra persona'],
            'comeEntreComidas': ['No', 'Fruta', 'Cereales', 'Productos lácteos', 'Bebidas excitantes', 'Alimentos altos en sal', 'Alimentos altos en azúcares', 'Alimentos altos en grasa'],
            'tipoDeApetito': ['Bueno', 'Malo', 'Regular'],
            'quGrasaUtilizan': ['Margarina', 'Mantequilla', 'Aceite vegetal', 'Manteca', 'Otros'],
            'horaHambre': ['00h00', '00h30', '01h00', '01h30', '02h00', '02h30', '03h00', '03h30', '04h00', '04h30', '05h00', '05h30', '06h00', '06h30', '07h00', '07h30', '08h00', '08h30', '09h00', '09h30', '10h00', '10h30', '11h00', '11h30', '12h00', '12h30', '13h00', '13h30', '14h00', '14h30', '15h00', '15h30', '16h00', '16h30', '17h00', '17h30', '18h00', '18h30', '19h00', '19h30', '20h00', '20h30', '21h00', '21h30', '22h00', '22h30', '23h00', '23h30'],
        },
        'links': {
            'paciente': 'Contact',
            'pedidos': 'Pedido',
        },
    },
    'Odontograma': {
        'label': 'Odontograma',
        'group': 'especialidad',
        'name': 'name',
        'links': {
            'paciente': 'Contact',
            'dientes': 'Diente',
        },
    },
    'Oficina': {
        'label': 'Oficina / Sucursal',
        'group': 'comercial',
        'name': 'name',
        'links': {
            'oficinaUsuario': 'User',
            'empresa': 'Company',
            'facturas': 'Invoice',
            'ordenDeVenta': 'SalesOrder',
            'usuario': 'User',
            'puntosDeVenta': 'SalesPoint',
            'debtorTrans': 'DebtorTrans',
            'salesOrders': 'SalesOrders',
            'establecimiento': 'BranchOffice',
            'factura': 'Invoice',
            'libroDiarios': 'LibroDiario',
            'pagos': 'Pago',
        },
    },
    'OrdenDeTrabajo': {
        'label': 'Órden De Trabajo',
        'group': 'clinico',
        'name': 'name',
        'status': 'estado',
        'stream': True,
        'required': ['agudezaVisual'],
        'enums': {
            'estado': ['Borrador', 'Solicitado', 'Fabricado', 'En bodega', 'Entregado', 'Devuelto'],
            'tipo': ['Lentes con marco', 'Lentes sin marco', 'Lentes de contacto', 'Otros'],
            'estadoDePago': ['Borrador', 'Generada', 'Facturada', 'Cobrada Parcialmente', 'Cobrada en Totalidad', 'Cerrada'],
            'acciones': ['...', 'Calcular'],
        },
        'links': {
            'profesional': 'User',
            'agudezaVisual': 'AgudezaVisual',
            'paciente': 'Contact',
            'pagos': 'Pago',
        },
    },
    'Pago': {
        'label': 'Registro de Pago',
        'group': 'facturacion',
        'name': 'name',
        'stream': True,
        'enums': {
            'medio': ['Transferencia', 'Depósito', 'Cheque', 'Tarjeta', 'Efectivo'],
            'proveedor': ['Banco Amazonas', 'BANCO BOLIVARIANO', 'Banco Capital', 'Banco Citibank', 'BANCO D MIRO SA', 'Banco Guayaquil', 'BANCO DE LOJA', 'BANCO DE MACHALA', 'BANCO DEL AUSTRO', 'BANCO DEL INSTITUTO ECUATORIANO DE SEGURIDAD SOCIAL', 'BANCO DEL LITORAL', 'Banco Pacífico', 'BANCO DELBANK S.A.', 'BANCO GENERAL RUMINAHUI', 'BANCO INTERNACIONAL', 'Banco Pichincha', 'BANCO PROCREDIT', 'BANCO SOLIDARIO', 'MUTUALISTA PICHINCHA', 'Produbanco', 'PagoPlux', 'Payphone'],
        },
        'links': {
            'comprobante': 'Attachment',
            'consulta': 'Meeting',
            'plan': 'Plan',
            'ordenDeTrabajo': 'OrdenDeTrabajo',
            'oficina': 'Oficina',
        },
    },
    'ParametrosFactura': {
        'label': 'Parámetro de Factura',
        'group': 'facturacion',
        'name': 'name',
        'required': ['ruc'],
        'enums': {
            'obligadoALlevarContabilidad': ['Si', 'No'],
            'tipoDeAmbiente': ['1', '2'],
        },
    },
    'PaymentTerms': {
        'label': 'PaymentTerms',
        'group': 'facturacion',
        'name': 'name',
        'required': ['name'],
        'links': {
            'contacts': 'Contact',
        },
    },
    'Pedido': {
        'label': 'Pedido',
        'group': 'inventario',
        'name': 'name',
        'required': ['pedidosPaciente'],
        'datetimes': ['pedidoFecha'],
        'enums': {
            'pedidoTipo': ['EEG', 'TAC C', 'Laboratorio', 'RX', 'Endoscopía', 'Resonancia', 'Interconsulta', 'Otros'],
        },
        'links': {
            'pedidosPaciente': 'Contact',
            'nutricion': 'Nutricion',
        },
    },
    'Percentil': {
        'label': 'Percentil',
        'group': 'especialidad',
        'name': 'name',
        'required': ['name'],
    },
    'PesoTalla': {
        'label': 'PesoTalla',
        'group': 'especialidad',
        'name': 'name',
        'links': {
            'pacientetallas': 'Contact',
        },
    },
    'Pharmacies': {
        'label': 'Farmacia',
        'group': 'inventario',
        'name': 'name',
        'stream': True,
        'required': ['name'],
        'enums': {
            'pharmacyGroup': ['Branch', 'Associate', 'Partner', 'Franchise', 'Agent', 'Main'],
            'accountStatus': ['Active', 'Closed', 'Deactivated'],
        },
        'links': {
            'prscpackages': 'Prscpackage',
            'contacts': 'Contact',
            'prescription': 'Prescription',
            'prescriptions': 'Prescription',
            'account1': 'Account',
            'account': 'Account',
        },
    },
    'Plan': {
        'label': 'Plan de Suscripción',
        'group': 'comercial',
        'name': 'name',
        'status': 'estado',
        'stream': True,
        'enums': {
            'tipo': ['1 licencia', 'Paquete 3', 'Paquete 5', 'Paquete Medium', 'Paquete Max'],
            'vigencia': ['mensual', 'anual'],
            'soporte': ['Ninguno', '8 / 5', '24 / 7'],
            'estado': ['Activo', 'Suspendido', 'Cancelado'],
        },
        'links': {
            'usuarios': 'User',
            'casos': 'Case',
            'cuentas': 'Cuentas',
            'cliente': 'Account',
            'productos': 'Product',
            'prestador': 'User',
            'pagos': 'Pago',
            'contratos': 'Contrato',
            'convenios': 'Convenio',
        },
    },
    'Precio': {
        'label': 'Precio',
        'group': 'facturacion',
        'name': 'name',
        'stream': True,
        'required': ['name'],
        'links': {
            'product': 'Product',
        },
    },
    'PreguntaPruebaS': {
        'label': 'PreguntaPruebaS',
        'group': 'especialidad',
        'name': 'name',
        'required': ['name'],
        'enums': {
            'opciones6': ['1', '2', '3', '4', '5', '6', ''],
            'opcionesHabilitadas': ['2', '3', '4', '5', '6', 'VF', 'SN'],
            'opcionesVerdaderoFalso': ['Verdadero', 'Falso', ''],
            'opciones2': ['', '1', '2'],
            'opciones3': ['', '1', '2', '3'],
            'opciones4': ['', '1', '2', '3', '4'],
            'opciones5': ['', '1', '2', '3', '4', '5'],
            'opcionesSiNo': ['', 'Si', 'No'],
        },
        'links': {
            'fichaPrueba': 'FichaPrueba',
            'respuestasPruebaS': 'RespuestaPruebaS',
            'pruebaSicolgica': 'PruebaSicolgica',
            'imagen': 'Attachment',
        },
    },
    'Prescription': {
        'label': 'Prescription',
        'group': 'recetas',
        'name': 'name',
        'status': 'status',
        'stream': True,
        'required': ['member', 'planRefilldates', 'prescriptionDocuments'],
        'datetimes': ['dateEnd', 'dateStart'],
        'enums': {
            'status': ['Held', 'Expired', 'Cancelled', 'Registered', 'Requested'],
            'refillFrequency': ['Weekly', 'Biweekly', 'Monthly', 'Bimonthly', 'Trimonthly', 'Quarterly', 'HalfYearly', 'Yearly', 'Dates'],
            'preferredDeliverymode': ['Self', 'Home', 'Office'],
        },
        'links': {
            'accountClinic': 'Account',
            'prescriptionDocuments': 'Attachment',
            'prscpackages': 'Prscpackage',
            'member': 'Member',
            'cases': 'Case',
            'pharmacies': 'Pharmacies',
        },
    },
    'Prestador': {
        'label': 'Prestador',
        'group': 'comercial',
        'name': 'name',
        'stream': True,
        'required': ['name'],
        'links': {
            'ubicaciones': 'UbicacionActivosFijos',
            'convenios': 'Convenio',
        },
    },
    'Prices': {
        'label': 'Prices',
        'group': 'facturacion',
        'name': 'name',
        'links': {
            'salesType': 'SalesType',
            'product': 'Product',
        },
    },
    'Procedimiento': {
        'label': 'Procedimiento',
        'group': 'clinico',
        'name': 'name',
        'stream': True,
        'required': ['name'],
        'enums': {
            'tipo': ['Odontológico', 'Cirugía', 'Dermatológico'],
        },
        'links': {
            'ciclo': 'Sesion',
            'diente': 'Diente',
            'tratamientoOdontologicos': 'TratamientoOdontologico',
        },
    },
    'Product': {
        'label': 'Producto',
        'group': 'inventario',
        'name': 'name',
        'stream': True,
        'required': ['code', 'shortName'],
        'enums': {
            'codigoDeDesecho': ['Y1', 'Y2', 'Y3', 'Y4', 'Y14', 'Y18'],
        },
        'links': {
            'consultas': 'Meeting',
            'productosRight': 'Product',
            'productosLeft': 'Product',
            'atencion': 'Atencion',
            'precios': 'Precio',
            'debtorTransDetails': 'DebtorTransDetails',
            'planes': 'Plan',
            'tratamientoOdontologico': 'TratamientoOdontologico',
            'recetaProducto': 'RecetaProducto',
            'taxTypes': 'TaxTypes',
        },
    },
    'ProductBrand': {
        'label': 'Marca del Producto',
        'group': 'inventario',
        'enums': {
            'paisDeProcedencia': ['Ecuador', 'Estados Unidos', 'Chile', 'Argentina', 'Colombia', 'Perú', 'Bolivia', 'Brasil', 'Venezuela', 'Alemania', 'España', 'Francia', 'Italia', 'Uruguay', 'Paraguay'],
        },
        'links': {
            'medication': 'Medicationlist',
        },
    },
    'ProductCategory': {
        'label': 'Categoría del Producto',
        'group': 'inventario',
    },
    'ProtocoloCIAP': {
        'label': 'ProtocoloCIAP',
        'group': 'clinico',
        'name': 'name',
        'required': ['code'],
        'enums': {
            'componentes': ['', '1', '2', '3', '4', '5', '6', '7'],
        },
        'links': {
            'atenciones': 'Atencion',
            'idDiagnosticos': 'IdDiagnostico',
        },
    },
    'Proveedor': {
        'label': 'Proveedor',
        'group': 'inventario',
        'name': 'name',
        'enums': {
            'salutationName': ['', 'Mr.', 'Ms.', 'Mrs.', 'Dr.'],
        },
    },
    'Prscdspnlineitem': {
        'label': 'Prscdspnlineitem',
        'group': 'recetas',
        'name': 'name',
        'stream': True,
        'required': ['issuedNumbers', 'issuedQuantity', 'lineNumber', 'medicationlist', 'prscpackage', 'totalPrice', 'useDosage'],
        'links': {
            'prscpackage': 'Prscpackage',
            'medicationlist': 'Medicationlist',
        },
    },
    'Prscpackage': {
        'label': 'Paquete de Producto',
        'group': 'recetas',
        'name': 'name',
        'stream': True,
        'required': ['packageDescription', 'packageIssuedate', 'packageRefillnumber', 'requiredDeliverydate'],
        'enums': {
            'deliveryMode': ['Self', 'Home', 'Office', 'Address', 'None'],
            'deliveryStatus': ['Preparing', 'Despatched', 'Delivered', 'Delayed', 'Returned', 'Cancelled', 'Waiting', 'Ready', 'PickedUp', 'Paid', 'Collected'],
            'paymentmode': ['Cash', 'Claim', 'Card'],
        },
        'links': {
            'member': 'Member',
            'prescription': 'Prescription',
            'courier': 'Courier',
            'pharmacies': 'Pharmacies',
            'prscdspnlineitems': 'Prscdspnlineitem',
        },
    },
    'PruebaSicolgica': {
        'label': 'PruebaSicolgica',
        'group': 'especialidad',
        'name': 'name',
        'status': 'estado',
        'stream': True,
        'datetimes': ['fechaDeEnvio', 'fechaDeEvaluacion'],
        'enums': {
            'enviar': ['.', 'Crear Preguntas', 'Enviar', 'Evaluar'],
            'estado': ['Nueva', 'Creada', 'Enviada', 'Respondida', 'Calificada'],
        },
        'links': {
            'paciente': 'Contact',
            'fichaPrueba': 'FichaPrueba',
            'evaluador': 'User',
            'preguntasPrueba': 'PreguntaPruebaS',
            'respuestasPrueba': 'RespuestaPruebaS',
        },
    },
    'Quote': {
        'label': 'Cotización',
        'group': 'facturacion',
        'name': 'name',
        'enums': {
            'facturacionElectronica': ['SELECCIONE UNA OPCION', 'LISTA PARA ENVIAR', 'GENERADA', 'FIRMADA', 'ENVIADA SRI', 'AUTORIZADA', 'ENVIADA POR CORREO', 'ERROR'],
            'tipoDeAmbiente': ['1', '2'],
            'acciones': ['---', 'Facturar', 'Cancelar'],
        },
        'links': {
            'consulta': 'Meeting',
            'cuenta': 'Cuentas',
            'courier': 'Courier',
        },
    },
    'QuoteItem': {
        'label': 'Artículo cotizado',
        'group': 'facturacion',
    },
    'Receta': {
        'label': 'Receta',
        'group': 'recetas',
        'name': 'name',
        'status': 'recetaEstado',
        'required': ['idDiagnosticos', 'recetaMedicacion'],
        'enums': {
            'recetaEstado': ['activa', 'anulada'],
            'accion': ['...', 'Enviar a Paciente', 'Enviar por Correo'],
        },
        'links': {
            'meeting': 'Meeting',
            'contact': 'Contact',
            'idDiagnosticos': 'IdDiagnostico',
            'wischats': 'Wischat',
            'recetaProductos': 'RecetaProducto',
        },
    },
    'RecetaOftalmologica': {
        'label': 'Consulta Oftalmológica',
        'group': 'especialidad',
        'name': 'name',
        'stream': True,
        'datetimes': ['fechaDeRealizacion'],
        'enums': {
            'tipo': ['Emitida', 'Recibida'],
            'puntuacionSchirmerOI': ['N/D', 'Variable - [1]', '<=10 - [2]', '<= 5 - [3]', '<=2 - [4]'],
            'puntuacionSchirmerOD': ['N/D', 'Variable - [1]', '<=10 - [2]', '<= 5 - [3]', '<=2 - [4]'],
            'testButOI': ['N/D', 'Variable - [1]', '<=10 - [2]', '<= 5 - [3]', 'Inmediato - [4]'],
            'testButOD': ['N/D', 'Variable - [1]', '<=10 - [2]', '<= 5 - [3]', 'Inmediato - [4]'],
        },
        'links': {
            'paciente': 'Contact',
            'diagnosticosOI': 'IdDiagnostico',
            'diagnosticosOD': 'IdDiagnostico',
            'profesional': 'User',
            'tarea': 'Task',
            'resultadosFO': 'Attachment',
            'examenes': 'Attachment',
        },
    },
    'RecetaProducto': {
        'label': 'RecetaProducto',
        'group': 'recetas',
        'name': 'name',
        'links': {
            'producto': 'Product',
            'receta': 'Receta',
        },
    },
    'Recurrente': {
        'label': 'Recurrente',
        'group': 'actividad',
        'name': 'name',
        'status': 'status',
        'stream': True,
        'required': ['dateEnd', 'name'],
        'datetimes': ['dateEnd', 'dateStart'],
        'enums': {
            'status': ['Planned', 'Held', 'Not Held'],
            'recurrencia': ['Diario', 'Semanal', 'Mensual', 'Anual'],
        },
        'links': {
            'tareas': 'Task',
            'profesional': 'User',
        },
    },
    'Red': {
        'label': 'Red',
        'group': 'comercial',
        'name': 'name',
        'stream': True,
        'required': ['name'],
        'enums': {
            'type': ['Meet', 'Zoom', 'WhatsApp', 'YoPagoFacil'],
        },
        'links': {
            'user': 'User',
        },
    },
    'Reflines': {
        'label': 'Reflines',
        'group': 'facturacion',
        'name': 'name',
        'required': ['name'],
    },
    'ReportCategory': {
        'label': 'Categoría de Reportes',
        'group': 'administracion',
    },
    'RespuestaPruebaS': {
        'label': 'RespuestaPruebaS',
        'group': 'especialidad',
        'name': 'name',
        'required': ['name'],
        'links': {
            'preguntaPruebaS': 'PreguntaPruebaS',
            'paciente': 'Contact',
            'fichaPrueba': 'FichaPrueba',
            'pruebaSicolgica': 'PruebaSicolgica',
        },
    },
    'Resultados': {
        'label': 'Resultado',
        'group': 'especialidad',
        'name': 'name',
        'stream': True,
        'datetimes': ['fechaAnalisis'],
        'enums': {
            'estado': ['Solicitado', 'Pendiente revisión', 'Completado', 'Rechazado'],
        },
        'links': {
            'pacienteresultados': 'Contact',
            'valores': 'Valor',
        },
    },
    'SalesGroup': {
        'label': 'SalesGroup',
        'group': 'facturacion',
        'name': 'name',
        'required': ['name'],
        'links': {
            'custBranchs': 'CustBranch',
            'contact': 'Contact',
        },
    },
    'SalesOrder': {
        'label': 'SalesOrder',
        'group': 'facturacion',
        'links': {
            'oficinas': 'Oficina',
        },
    },
    'SalesOrderDetails': {
        'label': 'SalesOrderDetails',
        'group': 'facturacion',
        'name': 'name',
        'required': ['product'],
        'links': {
            'salesOrders': 'SalesOrders',
            'product': 'Product',
        },
    },
    'SalesOrders': {
        'label': 'SalesOrders',
        'group': 'facturacion',
        'name': 'name',
        'stream': True,
        'required': ['contact'],
        'enums': {
            'salutationName': ['', 'Mr.', 'Ms.', 'Mrs.', 'Dr.'],
            'transType': ['30', '32'],
            'convertSalesOrder': ['', 'salesOrder'],
            'convertDebtorTrans': ['', 'deliveryNote', 'invoice'],
        },
        'links': {
            'contact': 'Contact',
            'location': 'Location',
            'shippingProvider': 'ShippingProvider',
            'salesOrderDetailses': 'SalesOrderDetails',
            'quoteParent': 'SalesOrders',
            'salesOrdersParent': 'SalesOrders',
            'debtorTrans': 'DebtorTrans',
            'oficinas': 'Oficina',
        },
    },
    'SalesPoint': {
        'label': 'Punto de Venta',
        'group': 'facturacion',
        'name': 'name',
        'required': ['empresa', 'ptoEmi'],
        'enums': {
            'tipoDeAmbiente': ['1', '2'],
        },
        'links': {
            'debtorTranses': 'DebtorTrans',
            'profesionales': 'User',
            'users': 'User',
            'oficina': 'Oficina',
            'empresa': 'Company',
            'facturas': 'Invoice',
        },
    },
    'SalesType': {
        'label': 'Tipo de Venta',
        'group': 'facturacion',
        'name': 'name',
        'required': ['name'],
        'links': {
            'prices': 'Prices',
            'accounts': 'Account',
        },
    },
    'Sesion': {
        'label': 'Ciclo de Sesión',
        'group': 'clinico',
        'name': 'name',
        'status': 'status',
        'stream': True,
        'required': ['dateEnd'],
        'datetimes': ['dateEnd', 'dateStart'],
        'enums': {
            'status': ['Borrador', 'Planned', 'En desarrollo', 'Held', 'Not Held', 'Incompleto', 'Cancelado', 'Error'],
            'acciones': ['Borrador', 'Programar', 'Cancelar', 'Terminar'],
            'recurrencia': ['Anual', 'Mensual', 'Semanal', 'Diario'],
        },
        'links': {
            'consulta': 'Meeting',
            'procedimientos': 'Procedimiento',
            'paciente': 'Contact',
            'profesionales': 'User',
        },
    },
    'ShippingProvider': {
        'label': 'ShippingProvider',
        'group': 'inventario',
        'links': {
            'salesOrders': 'SalesOrders',
            'custBranchs': 'CustBranch',
            'contact': 'Contact',
            'debtorTrans': 'DebtorTrans',
            'facturas': 'Invoice',
        },
    },
    'SignosVitales': {
        'label': 'Signos Vitales',
        'group': 'clinico',
        'name': 'name',
        'stream': True,
        'datetimes': ['fechaDeTomaDeDatos'],
        'enums': {
            'tipoTemperatura': ['Boca', 'Oído', 'Recto', 'Axila', 'Frente'],
            'escalaGlasgow': ['1/15', '2/15', '3/15', '4/15', '5/15', '6/15', '7/15', '8/15', '9/15', '10/15', '11/15', '12/15', '13/15', '14/15', '15/15'],
        },
        'links': {
            'pacientesignos': 'Contact',
            'atencion': 'Atencion',
        },
    },
    'StockMoves': {
        'label': 'StockMoves',
        'group': 'inventario',
        'name': 'name',
        'enums': {
            'type': ['16', '17', '21', '22', '25', '28', '29', '35'],
        },
        'links': {
            'product': 'Product',
            'location': 'Location',
        },
    },
    'Subscriptionplan': {
        'label': 'Subscriptionplan',
        'group': 'comercial',
        'name': 'name',
        'required': ['name'],
    },
    'Supplier': {
        'label': 'Supplier',
        'group': 'inventario',
        'name': 'name',
        'required': ['name'],
    },
    'Supply': {
        'label': 'Supply',
        'group': 'inventario',
        'name': 'name',
        'required': ['lastName'],
        'enums': {
            'salutationName': ['', 'Mr.', 'Ms.', 'Mrs.', 'Dr.'],
            'estado': ['Registro de compras paso 1', 'Registro de compra paso 2', 'Registro de compras paso 3'],
        },
    },
    'Sync': {
        'label': 'Sync',
        'group': 'fhir',
        'name': 'name',
        'required': ['name'],
    },
    'Tarifario': {
        'label': 'Tarifario',
        'group': 'facturacion',
        'name': 'name',
        'stream': True,
        'required': ['name'],
        'enums': {
            'estado': ['Activo', 'Inactivo'],
        },
        'links': {
            'tarifarios': 'Tarifario',
            'tarifarioParent': 'Tarifario',
            'convenio': 'Convenio',
            'archivosDeSoporte': 'Attachment',
        },
    },
    'Task': {
        'label': 'Actividad',
        'group': 'actividad',
        'name': 'name',
        'status': 'status',
        'stream': True,
        'enums': {
            'actividadTiempo': ['15', '30', '45', '60'],
            'actividadTipo': ['presencial', 'tele', 'domicilio', 'entrega'],
        },
        'links': {
            'pacientes': 'Contact',
            'tareaprofesional': 'User',
            'recetaOftalmologica': 'RecetaOftalmologica',
            'consulta': 'Meeting',
        },
    },
    'TaxGroups': {
        'label': 'Grupo de impuestos (Tabla 16)',
        'group': 'facturacion',
        'name': 'name',
        'stream': True,
        'required': ['name'],
        'links': {
            'products': 'Product',
            'taxTypes': 'TaxTypes',
        },
    },
    'TaxTypes': {
        'label': 'Tipo de impuesto (16+17)',
        'group': 'facturacion',
        'name': 'name',
        'required': ['name', 'taxRateCode'],
        'links': {
            'purchasingGlCode': 'ChartMaster',
            'salesGlCode': 'ChartMaster',
            'taxGroups': 'TaxGroups',
            'invoiceItem': 'InvoiceItem',
            'productos': 'Product',
        },
    },
    'TractoGenital': {
        'label': 'TractoGenital',
        'group': 'especialidad',
        'name': 'name',
        'stream': True,
        'required': ['name'],
        'enums': {
            'examen': ['EPelvico', 'Papanicolaou', 'Colposcopia', 'Biopsia', 'TAC', 'RM', 'radiografia', 'TEP', 'Proctosigmoidoscopia', 'Cistoscopia'],
        },
        'links': {
            'controlTGpaciente': 'Contact',
        },
    },
    'TransTaxDetails': {
        'label': 'Detalle de impuesto',
        'group': 'facturacion',
        'name': 'name',
        'required': ['name'],
        'links': {
            'debtorTransDetails': 'DebtorTransDetails',
            'invoiceItem': 'InvoiceItem',
        },
    },
    'TratamientoOdontologico': {
        'label': 'TratamientoOdontologico',
        'group': 'especialidad',
        'name': 'name',
        'stream': True,
        'required': ['name'],
        'links': {
            'diente': 'Diente',
            'procedimiento': 'Procedimiento',
            'producto': 'Product',
        },
    },
    'UbicacionActivosFijos': {
        'label': 'Ubicación Activos Fijos',
        'group': 'contabilidad',
        'name': 'name',
        'required': ['name'],
        'links': {
            'facturas': 'Invoice',
            'prestador': 'Prestador',
        },
    },
    'User': {
        'label': 'User',
        'group': 'administracion',
        'enums': {
            'acciones': ['', 'Generar Cuenta'],
            'tipoIdentificacion': ['RUC', 'CÉDULA', 'PASAPORTE'],
        },
        'links': {
            'usuarioLogo': 'Attachment',
            'oficinas': 'Oficina',
            'categorias': 'Categoria',
            'task': 'Task',
            'red': 'Red',
            'cuentas': 'Cuentas',
            'certificado': 'Certificado',
            'consentimientos': 'Consentimiento',
            'empresas': 'Company',
            'salesPoint': 'SalesPoint',
            'sucursales': 'CustBranch',
            'oficinaUsuarios': 'Oficina',
            'userAprobador': 'User',
            'usuario': 'User',
            'userParent': 'User',
            'usuarios': 'User',
            'planws': 'Plan',
            'pruebaSicolgica': 'PruebaSicolgica',
            'cuentaCliente': 'Account',
            'planes': 'Plan',
            'cuenta': 'Account',
            'registrosAgudezaVisual': 'AgudezaVisual',
            'recetaOftalmologicas': 'RecetaOftalmologica',
            'sesiones': 'Sesion',
            'ordenesDeTrabajo': 'OrdenDeTrabajo',
            'contratos': 'Contrato',
        },
    },
    'VaccinationProtocol': {
        'label': 'VaccinationProtocol',
        'group': 'especialidad',
        'name': 'name',
        'required': ['name'],
    },
    'Vacuna': {
        'label': 'Vacuna',
        'group': 'especialidad',
        'name': 'name',
        'stream': True,
        'required': ['name'],
        'links': {
            'inmunizacion': 'Inmunizacin',
        },
    },
    'Valor': {
        'label': 'Valor',
        'group': 'especialidad',
        'name': 'name',
        'stream': True,
        'required': ['codigo', 'name'],
        'enums': {
            'muestra': ['Suero', 'Plasma', 'Orina', 'Cefalorraquídeo', 'Fecal', 'Otros'],
        },
        'links': {
            'resultado': 'Resultados',
        },
    },
    'VoipMessage': {
        'label': 'VoipMessage',
        'group': 'comunicaciones',
    },
    'Whatsapp': {
        'label': 'Whatsapp',
        'group': 'comunicaciones',
        'name': 'name',
    },
    'Wischat': {
        'label': 'WhatsApp',
        'group': 'comunicaciones',
        'name': 'name',
        'stream': True,
        'datetimes': ['timestamp'],
        'enums': {
            'estado': ['Enviando ...', 'Enviado', 'En espera', 'Error', 'Recibido'],
        },
        'links': {
            'paciente': 'Contact',
            'consultas': 'Meeting',
            'certificado': 'Certificado',
            'receta': 'Receta',
        },
    },
}


def describe_catalog_entry(name: str) -> dict[str, Any] | None:
    """La ficha del catálogo para `name`, o None si QMedic no la define."""
    entry = QMEDIC_ENTITIES.get(name)
    if entry is None:
        return None
    return {"entity": name, **entry, "source": "catalog"}


def entities_in_group(group: str) -> list[str]:
    """Nombres de entidad del grupo, ordenados."""
    return sorted(
        name for name, entry in QMEDIC_ENTITIES.items() if entry['group'] == group
    )
