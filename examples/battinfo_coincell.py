# python
# python
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Union

from pydantic import ConfigDict, Field

# based on pydantic v2
from oold.model import LinkedBaseModel  # noqa
from oold.model import ResolveParam  # noqa
from oold.model import Resolver  # noqa
from oold.model import ResolveResult  # noqa
from oold.model import SetResolverParam  # noqa
from oold.model import set_resolver  # noqa

try:
    from yourpkg import LinkedBaseModel
except Exception:
    from pydantic import BaseModel as LinkedBaseModel

from pydantic import ConfigDict

# Common prefixes and BASE context (unchanged)
COMMON_PREFIXES = {
    "id": "@id",
    "type": "@type",
    "schema": "https://schema.org",
    "emmo": "https://w3id.org/emmo#",
    "echem": "https://w3id.org/emmo/domain/electrochemistry#",
    "battery": "https://w3id.org/emmo/domain/battery#",
    "chemical": "https://w3id.org/emmo/domain/chemical-substance/context",
    "unit": "https://qudt.org/vocab/unit/",
    "rdfs": "https://www.w3.org/TR/rdf-schema/#ch_comment",
}
BASE_CTX = [
    "https://w3id.org/emmo/domain/battery/context",
    COMMON_PREFIXES,
]


# Units (unchanged)
class EmmoUnit(str, Enum):
    micro_metre = "emmo:MicroMetre"
    unit_one = "emmo:UnitOne"
    volt = "emmo:Volt"
    milli_ampere_per_square_centi_metre = "emmo:MilliAmperePerSquareCentiMetre"
    milli_ampere_hour_per_square_centi_metre = "emmo:MilliAmpereHourPerSquareCentiMetre"
    gram_per_cubic_centi_metre = "emmo:GramPerCubicCentiMetre"
    celsius_temperature = "emmo:CelsiusTemperature"


class QudtUnit(str, Enum):
    percent = "unit:PERCENT"
    milli_gm_per_centi_m2 = "unit:MilliGM-PER-CentiM2"
    milli_a_hr_per_gm = "unit:MilliA-HR-PER-GM"
    milli_m = "unit:MilliM"
    milli_s_per_centi_m = "unit:MilliS-PER-CentiM"
    milli_pa_sec = "unit:MilliPA-SEC"
    mol_per_l = "unit:MOL-PER-L"


class EmmoClass(str, Enum):
    real_data = "emmo:RealData"
    spacer = "emmo:Spacer"


# New grouped enums for type-like literals and property kinds (CamelCase + human label as trailing string)
class SchemaType(str, Enum):
    Person = "schema:Person"
    "Person"


class DomainType(str, Enum):
    CoinCell = "CoinCell"
    "Coin Cell"
    Electrode = "Electrode"
    "Electrode"
    CurrentCollector = "CurrentCollector"
    "Current Collector"
    ElectrodeCoating = "ElectrodeCoating"
    "Electrode Coating"
    Binder = "Binder"
    "Binder"
    ConductiveAdditive = "ConductiveAdditive"
    "Conductive Additive"
    BatteryTest = "BatteryTest"
    "Battery Test"
    ElectrochemicalCell = "ElectrochemicalCell"
    "Electrochemical Cell"
    ElectrochemicalHalfCell = "ElectrochemicalHalfCell"
    "Electrochemical Half Cell"
    BatteryTestObject = "BatteryTestObject"
    "Battery Test Object"
    TaskStep = "TaskStep"
    "Task Step"
    MeasurementParameter = "MeasurementParameter"
    "Measurement Parameter"
    Solvent = "Solvent"
    "Solvent"
    SolventComponent = "SolventComponent"
    "Solvent Component"
    Solute = "Solute"
    "Solute"
    SoluteComponent = "SoluteComponent"
    "Solute Component"
    Additive = "Additive"
    "Additive"
    AdditiveComponent = "AdditiveComponent"
    "Additive Component"
    OrganicElectrolyte = "OrganicElectrolyte"
    "Organic Electrolyte"
    Separator = "Separator"
    "Separator"
    Case = "Case"
    "Case"
    CaseConstituents = "CaseConstituents"
    "Case Constituents"
    CellLid = "CellLid"
    "Cell Lid"
    CellCan = "CellCan"
    "Cell Can"
    Spring = "Spring"
    "Spring"
    Spacer = "Spacer"
    "Spacer"
    TopConstituents = "TopConstituents"
    "Top Constituents"
    NamedNode = "NamedNode"
    "Named Node"


class MaterialType(str, Enum):
    Aluminium = "Aluminium"
    "Aluminium"
    Copper = "Copper"
    "Copper"
    PolyvinylideneFluoride = "PolyvinylideneFluoride"
    "Polyvinylidene Fluoride"
    CarbonBlack = "CarbonBlack"
    "Carbon Black"
    Graphite = "Graphite"
    "Graphite"
    Polypropylene = "Polypropylene"
    "Polypropylene"
    R2032 = "R2032"
    "R2032"
    StainlessSteel = "StainlessSteel"
    "Stainless Steel"
    LithiumElectrode = "LithiumElectrode"
    "Lithium Electrode"
    EthyleneCarbonate = "EthyleneCarbonate"
    "Ethylene Carbonate"
    EthylMethylCarbonate = "EthylMethylCarbonate"
    "Ethyl Methyl Carbonate"
    LithiumHexafluorophosphate = "LithiumHexafluorophosphate"
    "Lithium Hexafluorophosphate"
    LithiumBisfluorosulfonylimide = "LithiumBisfluorosulfonylimide"
    "Lithium Bisfluorosulfonylimide"
    VinyleneCarbonate = "VinyleneCarbonate"
    "Vinylene Carbonate"
    TrisTrimethylsilyPhosphite = "TrisTrimethylsilyPhosphite"
    "Tris Trimethylsily Phosphite"


class OrgName(str, Enum):
    Customcells = "Customcells"
    "Customcells"
    Solvionic = "Solvionic"
    "Solvionic"
    Celgard = "Celgard"
    "Celgard"
    Hosen = "Hosen"
    "Hosen"


class MeasuredPropertyType(str, Enum):
    Thickness = "Thickness"
    "Thickness"
    MassFraction = "MassFraction"
    "Mass Fraction"
    MassLoading = "MassLoading"
    "Mass Loading"
    D50ParticleSize = "D50ParticleSize"
    "D50 Particle Size"
    CalenderedCoatingThickness = "CalenderedCoatingThickness"
    "Calendered Coating Thickness"
    Porosity = "Porosity"
    "Porosity"
    Tortuosity = "Tortuosity"
    "Tortuosity"
    RatedCapacity = "RatedCapacity"
    "Rated Capacity"
    ElectricCurrentDensity = "ElectricCurrentDensity"
    "Electric Current Density"
    UpperVoltageLimit = "UpperVoltageLimit"
    "Upper Voltage Limit"
    TerminationQuantity = "TerminationQuantity"
    "Termination Quantity"
    Voltage = "Voltage"
    "Voltage"
    LowerCurrentDensityLimit = "LowerCurrentDensityLimit"
    "Lower Current Density Limit"
    LowerVoltageLimit = "LowerVoltageLimit"
    "Lower Voltage Limit"
    ElectrolyticConductivity = "ElectrolyticConductivity"
    "Electrolytic Conductivity"
    DynamicViscosity = "DynamicViscosity"
    "Dynamic Viscosity"
    Density = "Density"
    "Density"
    CelsiusTemperature = "CelsiusTemperature"
    "Celsius Temperature"
    Diameter = "Diameter"
    "Diameter"
    AmountConcentration = "AmountConcentration"
    "Amount Concentration"
    VolumeFraction = "VolumeFraction"
    "Volume Fraction"


class ProcedureType(str, Enum):
    ConstantCurrentConstantVoltageCycling = "ConstantCurrentConstantVoltageCycling"
    "Constant Current Constant Voltage Cycling"


class TaskType(str, Enum):
    Charging = "Charging"
    "Charging"
    Discharging = "Discharging"
    "Discharging"
    Hold = "Hold"
    "Hold"


# Types for @type values: allow enums or plain strings (backward compatible)
NodeAtom = Union[
    str,
    SchemaType,
    DomainType,
    MaterialType,
    OrgName,
    MeasuredPropertyType,
    ProcedureType,
    TaskType,
    EmmoClass,
]
NodeType = Union[NodeAtom, List[NodeAtom]]


class Entity(LinkedBaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": BASE_CTX,
            "iri": "Entity",
        }
    )
    id: Optional[str] = None
    type: Optional[NodeType] = None


class SchemaPerson(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": ["Entity", {"name": "schema:name"}],
            "iri": "SchemaPerson",
        }
    )
    type: Optional[NodeType] = SchemaType.Person
    name: str


class SchemaOrganization(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": ["Entity", {"name": "schema:name"}],
            "iri": "SchemaOrganization",
        }
    )
    name: Optional[str] = None


class SchemaProductId(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": ["Entity", {"rdfs_comment": "rdfs:comment"}],
            "iri": "SchemaProductId",
        }
    )
    rdfs_comment: Union[str, int]


class MolecularFormula(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": ["Entity", {"rdfs_comment": "rdfs:comment"}],
            "iri": "MolecularFormula",
        }
    )
    rdfs_comment: str


class RealData(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": ["Entity", {"number_value": "hasNumberValue"}],
            "iri": "RealData",
        }
    )
    type: Optional[NodeType] = EmmoClass.real_data
    number_value: Union[int, float]


class ReverseEdge(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "output": {
                        "@id": "https://w3id.org/emmo#EMMO_c4bace1d_4db0_4cd3_87e9_18122bae2840",
                        "@type": "@id",
                    }
                },
            ],
            "iri": "ReverseEdge",
        }
    )
    output: Optional["BatteryTest"] = None


class MeasuredProperty(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "numerical_part": {
                        "@id": "https://w3id.org/emmo#EMMO_8ef3cd6d_ae58_4a8d_9fc0_ad8f49015cd0",
                        "@type": "@id",
                    },
                    "measurement_unit": {
                        "@id": "https://w3id.org/emmo#EMMO_bed1d005_b04e_4a90_94cf_02bc678a8569",
                        "@type": "@id",
                    },
                    "reverse": "@reverse",
                },
            ],
            "iri": "MeasuredProperty",
        }
    )
    numerical_part: Optional[RealData] = None
    measurement_unit: Optional[Union[EmmoUnit, QudtUnit, str]] = None
    reverse: Optional[ReverseEdge] = None


class NamedNode(Entity):
    model_config = ConfigDict(
        json_schema_extra={"@context": ["Entity.json"], "iri": "NamedNode.json"}
    )
    pass


class CoatingInfo(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": ["Entity", {"rdfs_comment": "rdfs:comment"}],
            "iri": "CoatingInfo",
        }
    )
    rdfs_comment: Optional[Union[str, int]] = None


class CurrentCollector(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "measured_property": {
                        "@id": "https://w3id.org/emmo#EMMO_fd689787_31b0_41cf_bf03_0d69af76469d",
                        "@type": "@id",
                    }
                },
            ],
            "iri": "CurrentCollector",
        }
    )
    measured_property: Optional[MeasuredProperty] = None


class ActiveMaterial(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "rdfs_comment": "rdfs:comment",
                    "molecular_formula": {
                        "@id": "https://w3id.org/emmo#EMMO_b8c10b72_7cc1_4e82_b4ab_728faf504919",
                        "@type": "@id",
                    },
                    "measured_property": {
                        "@id": "https://w3id.org/emmo#EMMO_fd689787_31b0_41cf_bf03_0d69af76469d",
                        "@type": "@id",
                    },
                },
            ],
            "iri": "ActiveMaterial",
        }
    )
    rdfs_comment: Optional[str] = None
    molecular_formula: Optional[MolecularFormula] = None
    measured_property: Optional[List[MeasuredProperty]] = None


class Binder(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "measured_property": {
                        "@id": "https://w3id.org/emmo#EMMO_fd689787_31b0_41cf_bf03_0d69af76469d",
                        "@type": "@id",
                    }
                },
            ],
            "iri": "Binder",
        }
    )
    measured_property: Optional[MeasuredProperty] = None


class ConductiveAdditive(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "measured_property": {
                        "@id": "https://w3id.org/emmo#EMMO_fd689787_31b0_41cf_bf03_0d69af76469d",
                        "@type": "@id",
                    }
                },
            ],
            "iri": "ConductiveAdditive",
        }
    )
    measured_property: Optional[MeasuredProperty] = None


class ElectrodeCoating(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "active_material": {
                        "@id": "https://w3id.org/emmo/domain/electrochemistry#electrochemistry_860aa941_5ff9_4452_8a16_7856fad07bee",
                        "@type": "@id",
                    },
                    "binder": {
                        "@id": "https://w3id.org/emmo/domain/electrochemistry#electrochemistry_056a5fab_3d99_46bd_8eb1_6e89a368e1a7",
                        "@type": "@id",
                    },
                    "conductive_additive": {
                        "@id": "https://w3id.org/emmo/domain/electrochemistry#electrochemistry_c830c469_60c3_4380_8382_4df13a32a1e7",
                        "@type": "@id",
                    },
                    "measured_property": {
                        "@id": "https://w3id.org/emmo#EMMO_fd689787_31b0_41cf_bf03_0d69af76469d",
                        "@type": "@id",
                    },
                },
            ],
            "iri": "ElectrodeCoating",
        }
    )
    active_material: Optional[ActiveMaterial] = None
    binder: Optional[Binder] = None
    conductive_additive: Optional[ConductiveAdditive] = None
    measured_property: Optional[List[MeasuredProperty]] = None


class Electrode(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "current_collector": {
                        "@id": "https://w3id.org/emmo/domain/electrochemistry#electrochemistry_cc8c2c5d_cf3d_444d_a7e8_44ec4c06a88e",
                        "@type": "@id",
                    },
                    "coating": {
                        "@id": "https://w3id.org/emmo/domain/electrochemistry#electrochemistry_4df9926d_d4f2_4955_93f3_a03c5edc5383",
                        "@type": "@id",
                    },
                    "measured_property": {
                        "@id": "https://w3id.org/emmo#EMMO_fd689787_31b0_41cf_bf03_0d69af76469d",
                        "@type": "@id",
                    },
                    "schema_manufacturer": "schema:manufacturer",
                    "schema_product_id": "schema:productID",
                },
            ],
            "iri": "Electrode",
        }
    )
    current_collector: Optional[CurrentCollector] = None
    coating: Optional[ElectrodeCoating] = None
    measured_property: Optional[List[MeasuredProperty]] = None
    schema_manufacturer: Optional[SchemaOrganization] = None
    schema_product_id: Optional[Union[str, SchemaProductId]] = None


class SolventComponent(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "measured_property": {
                        "@id": "https://w3id.org/emmo#EMMO_fd689787_31b0_41cf_bf03_0d69af76469d",
                        "@type": "@id",
                    }
                },
            ],
            "iri": "SolventComponent",
        }
    )
    measured_property: Optional[MeasuredProperty] = None


class Solvent(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "constituent": {
                        "@id": "https://w3id.org/emmo#EMMO_dba27ca1_33c9_4443_a912_1519ce4c39ec",
                        "@type": "@id",
                    }
                },
            ],
            "iri": "Solvent",
        }
    )
    constituent: Optional[List[SolventComponent]] = None


class AdditiveComponent(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "measured_property": {
                        "@id": "https://w3id.org/emmo#EMMO_fd689787_31b0_41cf_bf03_0d69af76469d",
                        "@type": "@id",
                    }
                },
            ],
            "iri": "AdditiveComponent",
        }
    )
    measured_property: Optional[MeasuredProperty] = None


class Additive(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "constituent": {
                        "@id": "https://w3id.org/emmo#EMMO_dba27ca1_33c9_4443_a912_1519ce4c39ec",
                        "@type": "@id",
                    }
                },
            ],
            "iri": "Additive",
        }
    )
    constituent: Optional[List[AdditiveComponent]] = None


class SoluteComponent(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "measured_property": {
                        "@id": "https://w3id.org/emmo#EMMO_fd689787_31b0_41cf_bf03_0d69af76469d",
                        "@type": "@id",
                    }
                },
            ],
            "iri": "SoluteComponent",
        }
    )
    measured_property: Optional[MeasuredProperty] = None


class Solute(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "constituent": {
                        "@id": "https://w3id.org/emmo#EMMO_dba27ca1_33c9_4443_a912_1519ce4c39ec",
                        "@type": "@id",
                    },
                    "additive": {
                        "@id": "https://w3id.org/emmo/domain/electrochemistry#electrochemistry_7df82c48_b599_4b02_bef0_9facc9c39410",
                        "@type": "@id",
                    },
                },
            ],
            "iri": "Solute",
        }
    )
    constituent: Optional[List[SoluteComponent]] = None
    additive: Optional[Additive] = None


class OrganicElectrolyte(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "solvent": "hasSolvent",
                    "solute": "hasSolute",
                    "measured_property": "hasMeasuredProperty",
                    "schema_manufacturer": "schema:manufacturer",
                },
            ],
            "iri": "OrganicElectrolyte",
        }
    )
    solvent: Optional[Solvent] = None
    solute: Optional[Solute] = None
    measured_property: Optional[List[MeasuredProperty]] = None
    schema_manufacturer: Optional[SchemaOrganization] = None


class Separator(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "measured_property": {
                        "@id": "https://w3id.org/emmo#EMMO_fd689787_31b0_41cf_bf03_0d69af76469d",
                        "@type": "@id",
                    },
                    "schema_manufacturer": "schema:manufacturer",
                    "schema_product_id": "schema:productID",
                },
            ],
            "iri": "Separator",
        }
    )
    measured_property: Optional[List[MeasuredProperty]] = None
    schema_manufacturer: Optional[SchemaOrganization] = None
    schema_product_id: Optional[SchemaProductId] = None


class CellLid(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "coating": {
                        "@id": "https://w3id.org/emmo/domain/electrochemistry#electrochemistry_4df9926d_d4f2_4955_93f3_a03c5edc5383",
                        "@type": "@id",
                    }
                },
            ],
            "iri": "CellLid",
        }
    )
    coating: Optional[CoatingInfo] = None


class CellCan(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "coating": {
                        "@id": "https://w3id.org/emmo/domain/electrochemistry#electrochemistry_4df9926d_d4f2_4955_93f3_a03c5edc5383",
                        "@type": "@id",
                    }
                },
            ],
            "iri": "CellCan",
        }
    )
    coating: Optional[CoatingInfo] = None


class CaseConstituents(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "cell_lid": {
                        "@id": "https://w3id.org/emmo/domain/electrochemistry#electrochemistry_1e33e37e_d7c9_4701_ba6d_a09456a13aaf",
                        "@type": "@id",
                    },
                    "cell_can": {
                        "@id": "https://w3id.org/emmo/domain/electrochemistry#electrochemistry_4a5660bd_1c1a_40e5_8a41_463c720d3903",
                        "@type": "@id",
                    },
                },
            ],
            "iri": "CaseConstituents",
        }
    )
    cell_lid: Optional[CellLid] = None
    cell_can: Optional[CellCan] = None


class Case(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "constituent": {
                        "@id": "https://w3id.org/emmo#EMMO_dba27ca1_33c9_4443_a912_1519ce4c39ec",
                        "@type": "@id",
                    },
                    "schema_manufacturer": "schema:manufacturer",
                    "schema_product_id": "schema:productID",
                },
            ],
            "iri": "Case",
        }
    )
    constituent: Optional[CaseConstituents] = None
    schema_manufacturer: Optional[SchemaOrganization] = None
    schema_product_id: Optional[SchemaProductId] = None


class Spring(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "measured_property": {
                        "@id": "https://w3id.org/emmo#EMMO_fd689787_31b0_41cf_bf03_0d69af76469d",
                        "@type": "@id",
                    }
                },
            ],
            "iri": "Spring",
        }
    )
    measured_property: Optional[List[MeasuredProperty]] = None


class Spacer(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "measured_property": {
                        "@id": "https://w3id.org/emmo#EMMO_fd689787_31b0_41cf_bf03_0d69af76469d",
                        "@type": "@id",
                    }
                },
            ],
            "iri": "Spacer",
        }
    )
    measured_property: Optional[List[MeasuredProperty]] = None


class TopConstituents(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": ["Entity", {"spring": "Spring", "spacer": "Spacer"}],
            "iri": "TopConstituents",
        }
    )
    spring: Optional[Spring] = None
    spacer: Optional[Spacer] = None


class ElectrochemicalCell(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": ["Entity", {"negative_electrode": "hasNegativeElectrode"}],
            "iri": "ElectrochemicalCell",
        }
    )
    negative_electrode: Optional[NamedNode] = None


class ElectrochemicalHalfCell(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": ["Entity", {"reference_electrode": "hasReferenceElectrode"}],
            "iri": "ElectrochemicalHalfCell",
        }
    )
    reference_electrode: Optional[NamedNode] = None


class BatteryTestObject(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "electrochemical_cell": "ElectrochemicalCell",
                    "electrochemical_half_cell": "ElectrochemicalHalfCell",
                },
            ],
            "iri": "BatteryTestObject",
        }
    )
    electrochemical_cell: Optional[ElectrochemicalCell] = None
    electrochemical_half_cell: Optional[ElectrochemicalHalfCell] = None


class TaskStep(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": ["Entity", {"input": "hasInput", "next": "hasNext"}],
            "iri": "TaskStep",
        }
    )
    input: Optional[List[MeasuredProperty]] = None
    next: Optional["TaskStep"] = None


class MeasurementParameter(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "rdfs_label": "rdfs:label",
                    "rdfs_comment": "rdfs:comment",
                    "task": "hasTask",
                },
            ],
            "iri": "MeasurementParameter",
        }
    )
    rdfs_label: Optional[str] = None
    rdfs_comment: Optional[str] = None
    task: Optional[TaskStep] = None


class BatteryTest(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "test_object": "hasTestObject",
                    "measurement_parameter": "hasMeasurementParameter",
                },
            ],
            "iri": "BatteryTest",
        }
    )
    test_object: Optional[BatteryTestObject] = None
    measurement_parameter: Optional[MeasurementParameter] = None


class CoinCell(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity",
                {
                    "schema_version": "schema:version",
                    "schema_product_id": "schema:productID",
                    "schema_date_created": "schema:dateCreated",
                    "schema_creator": "schema:creator",
                    "rdfs_comment": "rdfs:comment",
                    "positive_electrode": "hasPositiveElectrode",
                    "negative_electrode": "hasNegativeElectrode",
                    "electrolyte": "hasElectrolyte",
                    "separator": "hasSeparator",
                    "case": "hasCase",
                    "constituent": "hasConstituent",
                },
            ],
            "iri": "CoinCell",
        }
    )
    type: Optional[NodeType] = DomainType.CoinCell
    schema_version: Optional[str] = None
    schema_product_id: Optional[Union[str, SchemaProductId]] = None
    schema_date_created: Optional[str] = None
    schema_creator: Optional[SchemaPerson] = None
    rdfs_comment: Optional[List[str]] = None
    positive_electrode: Optional[Electrode] = None
    negative_electrode: Optional[Electrode] = None
    electrolyte: Optional[OrganicElectrolyte] = None
    separator: Optional[Separator] = None
    case: Optional[Case] = None
    constituent: Optional[TopConstituents] = None


# resolve forward refs
ReverseEdge.model_rebuild()
MeasuredProperty.model_rebuild()
TaskStep.model_rebuild()
MeasurementParameter.model_rebuild()
BatteryTest.model_rebuild()
CoinCell.model_rebuild()


# Example instance using enums for type-like literals
example_coin_cell = CoinCell(
    type=DomainType.CoinCell,
    schema_version="1.1.9",
    schema_product_id="Empa-bco-000007",
    schema_date_created="16/6/2024",
    schema_creator=SchemaPerson(
        id="https://orcid.org/0000-0002-5003-1134",
        name="Corsin Battaglia",
    ),
    rdfs_comment=[
        "BattINFO Converter version: 0.0.1",
        "Software credit: This JSON-LD was created using BattINFO converter (https://battinfoconverter.streamlit.app/) version: 0.0.1 and the coin cell battery schema version: 1.1.9, this web application was developed at Empa, Swiss Federal Laboratories for Materials Science and Technology in the Laboratory Materials for Energy Conversion",
        "BattINFO CoinCellSchema version: 1.1.9",
        "Project: Battery2030+/PREMISE",
        "Assembled manually or by robot: manually",
        "Cell assembly sequence: CellCan, NegativeElectrode, Separator, 100.0 uL Electrolyte, PositiveElectrode, 1.0 mm Spacer, Spring, CellLid",
    ],
    positive_electrode=Electrode(
        type=DomainType.Electrode,
        current_collector=CurrentCollector(
            type=[DomainType.CurrentCollector, MaterialType.Aluminium],
            measured_property=MeasuredProperty(
                type=MeasuredPropertyType.Thickness,
                numerical_part=RealData(number_value=15),
                measurement_unit=EmmoUnit.micro_metre,
            ),
        ),
        coating=ElectrodeCoating(
            type=DomainType.ElectrodeCoating,
            active_material=ActiveMaterial(
                rdfs_comment="LithiumNickelCobaltManganeseOxide",
                molecular_formula=MolecularFormula(rdfs_comment="LiNi0.6Co0.2Mn0.2O2"),
                measured_property=[
                    MeasuredProperty(
                        type=MeasuredPropertyType.MassFraction,
                        numerical_part=RealData(number_value=96),
                        measurement_unit=QudtUnit.percent,
                    ),
                    MeasuredProperty(
                        type=MeasuredPropertyType.MassLoading,
                        numerical_part=RealData(number_value=6.6),
                        measurement_unit=QudtUnit.milli_gm_per_centi_m2,
                    ),
                    MeasuredProperty(
                        type=MeasuredPropertyType.D50ParticleSize,
                        numerical_part=RealData(number_value=8),
                        measurement_unit=EmmoUnit.micro_metre,
                    ),
                ],
            ),
            binder=Binder(
                type=[DomainType.Binder, MaterialType.PolyvinylideneFluoride],
                measured_property=MeasuredProperty(
                    type=MeasuredPropertyType.MassFraction,
                    numerical_part=RealData(number_value=2),
                    measurement_unit=QudtUnit.percent,
                ),
            ),
            conductive_additive=ConductiveAdditive(
                type=[DomainType.ConductiveAdditive, MaterialType.CarbonBlack],
                measured_property=MeasuredProperty(
                    type=MeasuredPropertyType.MassFraction,
                    numerical_part=RealData(number_value=2),
                    measurement_unit=QudtUnit.percent,
                ),
            ),
            measured_property=[
                MeasuredProperty(
                    type=MeasuredPropertyType.CalenderedCoatingThickness,
                    numerical_part=RealData(number_value=16),
                    measurement_unit=EmmoUnit.micro_metre,
                ),
                MeasuredProperty(
                    type=MeasuredPropertyType.Porosity,
                    numerical_part=RealData(number_value=35),
                    measurement_unit=QudtUnit.percent,
                ),
                MeasuredProperty(
                    type=MeasuredPropertyType.Tortuosity,
                    numerical_part=RealData(number_value=2.5),
                    measurement_unit=EmmoUnit.unit_one,
                ),
            ],
        ),
        measured_property=[
            MeasuredProperty(
                type=MeasuredPropertyType.RatedCapacity,
                reverse=ReverseEdge(
                    output=BatteryTest(
                        type=DomainType.BatteryTest,
                        test_object=BatteryTestObject(
                            electrochemical_cell=ElectrochemicalCell(
                                type=DomainType.ElectrochemicalCell,
                                negative_electrode=NamedNode(
                                    type=MaterialType.Graphite
                                ),
                            )
                        ),
                        measurement_parameter=MeasurementParameter(
                            type=[ProcedureType.ConstantCurrentConstantVoltageCycling],
                            rdfs_label="GeneratedBatteryTestProcedure",
                            rdfs_comment="A description of a generated battery testing procedure",
                            task=TaskStep(
                                type=TaskType.Charging,
                                input=[
                                    MeasuredProperty(
                                        type=MeasuredPropertyType.ElectricCurrentDensity,
                                        numerical_part=RealData(number_value=0.1),
                                        measurement_unit=EmmoUnit.milli_ampere_per_square_centi_metre,
                                    ),
                                    MeasuredProperty(
                                        type=[
                                            MeasuredPropertyType.UpperVoltageLimit,
                                            MeasuredPropertyType.TerminationQuantity,
                                        ],
                                        numerical_part=RealData(number_value=4.2),
                                        measurement_unit=EmmoUnit.volt,
                                    ),
                                ],
                                next=TaskStep(
                                    type=TaskType.Hold,
                                    input=[
                                        MeasuredProperty(
                                            type=MeasuredPropertyType.Voltage,
                                            numerical_part=RealData(number_value=4.2),
                                            measurement_unit=EmmoUnit.volt,
                                        ),
                                        MeasuredProperty(
                                            type=[
                                                MeasuredPropertyType.LowerCurrentDensityLimit,
                                                MeasuredPropertyType.TerminationQuantity,
                                            ],
                                            numerical_part=RealData(number_value=0.01),
                                            measurement_unit=EmmoUnit.milli_ampere_per_square_centi_metre,
                                        ),
                                    ],
                                    next=TaskStep(
                                        type=TaskType.Discharging,
                                        input=[
                                            MeasuredProperty(
                                                type=MeasuredPropertyType.ElectricCurrentDensity,
                                                numerical_part=RealData(
                                                    number_value=0.1
                                                ),
                                                measurement_unit=EmmoUnit.milli_ampere_per_square_centi_metre,
                                            ),
                                            MeasuredProperty(
                                                type=[
                                                    MeasuredPropertyType.LowerVoltageLimit,
                                                    MeasuredPropertyType.TerminationQuantity,
                                                ],
                                                numerical_part=RealData(
                                                    number_value=2.5
                                                ),
                                                measurement_unit=EmmoUnit.volt,
                                            ),
                                        ],
                                    ),
                                ),
                            ),
                        ),
                    )
                ),
            ),
            MeasuredProperty(
                type=MeasuredPropertyType.RatedCapacity,
                numerical_part=RealData(number_value=1.1),
                measurement_unit=EmmoUnit.milli_ampere_hour_per_square_centi_metre,
            ),
            MeasuredProperty(
                type=MeasuredPropertyType.RatedCapacity,
                numerical_part=RealData(number_value=160),
                measurement_unit=QudtUnit.milli_a_hr_per_gm,
            ),
            MeasuredProperty(
                type=MeasuredPropertyType.Diameter,
                numerical_part=RealData(number_value=12),
                measurement_unit=QudtUnit.milli_m,
            ),
        ],
        schema_manufacturer=SchemaOrganization(
            id="https://www.wikidata.org/wiki/Q120784603",
            type=OrgName.Customcells,
        ),
        schema_product_id=SchemaProductId(rdfs_comment=100000030),
    ),
    negative_electrode=Electrode(
        type=DomainType.Electrode,
        current_collector=CurrentCollector(
            type=[DomainType.CurrentCollector, MaterialType.Copper],
            measured_property=MeasuredProperty(
                type=MeasuredPropertyType.Thickness,
                numerical_part=RealData(number_value=14),
                measurement_unit=EmmoUnit.micro_metre,
            ),
        ),
        coating=ElectrodeCoating(
            type=DomainType.ElectrodeCoating,
            active_material=ActiveMaterial(
                type=MaterialType.Graphite,
                measured_property=[
                    MeasuredProperty(
                        type=MeasuredPropertyType.MassFraction,
                        numerical_part=RealData(number_value=95),
                        measurement_unit=QudtUnit.percent,
                    ),
                    MeasuredProperty(
                        type=MeasuredPropertyType.MassLoading,
                        numerical_part=RealData(number_value=3.4),
                        measurement_unit=QudtUnit.milli_gm_per_centi_m2,
                    ),
                    MeasuredProperty(
                        type=MeasuredPropertyType.D50ParticleSize,
                        numerical_part=RealData(number_value=10),
                        measurement_unit=EmmoUnit.micro_metre,
                    ),
                ],
            ),
            binder=Binder(
                type=[DomainType.Binder, MaterialType.PolyvinylideneFluoride],
                measured_property=MeasuredProperty(
                    type=MeasuredPropertyType.MassFraction,
                    numerical_part=RealData(number_value=3),
                    measurement_unit=QudtUnit.percent,
                ),
            ),
            conductive_additive=ConductiveAdditive(
                type=[DomainType.ConductiveAdditive, MaterialType.CarbonBlack],
                measured_property=MeasuredProperty(
                    type=MeasuredPropertyType.MassFraction,
                    numerical_part=RealData(number_value=2),
                    measurement_unit=QudtUnit.percent,
                ),
            ),
            measured_property=[
                MeasuredProperty(
                    type=MeasuredPropertyType.CalenderedCoatingThickness,
                    numerical_part=RealData(number_value=20),
                    measurement_unit=EmmoUnit.micro_metre,
                ),
                MeasuredProperty(
                    type=MeasuredPropertyType.Porosity,
                    numerical_part=RealData(number_value=34),
                    measurement_unit=QudtUnit.percent,
                ),
                MeasuredProperty(
                    type=MeasuredPropertyType.Tortuosity,
                    numerical_part=RealData(number_value=2.5),
                    measurement_unit=EmmoUnit.unit_one,
                ),
            ],
        ),
        measured_property=[
            MeasuredProperty(
                type=MeasuredPropertyType.RatedCapacity,
                reverse=ReverseEdge(
                    output=BatteryTest(
                        type=DomainType.BatteryTest,
                        test_object=BatteryTestObject(
                            electrochemical_half_cell=ElectrochemicalHalfCell(
                                type=DomainType.ElectrochemicalHalfCell,
                                reference_electrode=NamedNode(
                                    type=MaterialType.LithiumElectrode
                                ),
                            )
                        ),
                        measurement_parameter=MeasurementParameter(
                            type=[ProcedureType.ConstantCurrentConstantVoltageCycling],
                            rdfs_label="GeneratedBatteryTestProcedure",
                            rdfs_comment="A description of a generated battery testing procedure",
                            task=TaskStep(
                                type=TaskType.Discharging,
                                input=[
                                    MeasuredProperty(
                                        type=MeasuredPropertyType.ElectricCurrentDensity,
                                        numerical_part=RealData(number_value=0.1),
                                        measurement_unit=EmmoUnit.milli_ampere_per_square_centi_metre,
                                    ),
                                    MeasuredProperty(
                                        type=[
                                            MeasuredPropertyType.LowerVoltageLimit,
                                            MeasuredPropertyType.TerminationQuantity,
                                        ],
                                        numerical_part=RealData(number_value=0.01),
                                        measurement_unit=EmmoUnit.volt,
                                    ),
                                ],
                                next=TaskStep(
                                    type=TaskType.Hold,
                                    input=[
                                        MeasuredProperty(
                                            type=MeasuredPropertyType.Voltage,
                                            numerical_part=RealData(number_value=0.01),
                                            measurement_unit=EmmoUnit.volt,
                                        ),
                                        MeasuredProperty(
                                            type=[
                                                MeasuredPropertyType.LowerCurrentDensityLimit,
                                                MeasuredPropertyType.TerminationQuantity,
                                            ],
                                            numerical_part=RealData(number_value=0.01),
                                            measurement_unit=EmmoUnit.milli_ampere_per_square_centi_metre,
                                        ),
                                    ],
                                    next=TaskStep(
                                        type=TaskType.Charging,
                                        input=[
                                            MeasuredProperty(
                                                type=MeasuredPropertyType.ElectricCurrentDensity,
                                                numerical_part=RealData(
                                                    number_value=0.1
                                                ),
                                                measurement_unit=EmmoUnit.milli_ampere_per_square_centi_metre,
                                            ),
                                            MeasuredProperty(
                                                type=[
                                                    MeasuredPropertyType.LowerVoltageLimit,
                                                    MeasuredPropertyType.TerminationQuantity,
                                                ],
                                                numerical_part=RealData(
                                                    number_value=0.01
                                                ),
                                                measurement_unit=EmmoUnit.volt,
                                            ),
                                        ],
                                    ),
                                ),
                            ),
                        ),
                    )
                ),
            ),
            MeasuredProperty(
                type=MeasuredPropertyType.RatedCapacity,
                numerical_part=RealData(number_value=1.2),
                measurement_unit=EmmoUnit.milli_ampere_hour_per_square_centi_metre,
            ),
            MeasuredProperty(
                type=MeasuredPropertyType.RatedCapacity,
                numerical_part=RealData(number_value=350),
                measurement_unit=QudtUnit.milli_a_hr_per_gm,
            ),
            MeasuredProperty(
                type=MeasuredPropertyType.Diameter,
                numerical_part=RealData(number_value=14),
                measurement_unit=QudtUnit.milli_m,
            ),
        ],
        schema_manufacturer=SchemaOrganization(
            id="https://www.wikidata.org/wiki/Q120784603",
            type=OrgName.Customcells,
        ),
        schema_product_id=SchemaProductId(rdfs_comment="11113, A-1594"),
    ),
    electrolyte=OrganicElectrolyte(
        type=DomainType.OrganicElectrolyte,
        solvent=Solvent(
            constituent=[
                SolventComponent(
                    type=MaterialType.EthyleneCarbonate,
                    measured_property=MeasuredProperty(
                        type=MeasuredPropertyType.VolumeFraction,
                        numerical_part=RealData(number_value=30),
                        measurement_unit=QudtUnit.percent,
                    ),
                ),
                SolventComponent(
                    type=MaterialType.EthylMethylCarbonate,
                    measured_property=MeasuredProperty(
                        type=MeasuredPropertyType.VolumeFraction,
                        numerical_part=RealData(number_value=70),
                        measurement_unit=QudtUnit.percent,
                    ),
                ),
            ]
        ),
        solute=Solute(
            type=DomainType.Solute,
            constituent=[
                SoluteComponent(
                    type=MaterialType.LithiumHexafluorophosphate,
                    measured_property=MeasuredProperty(
                        type=MeasuredPropertyType.AmountConcentration,
                        numerical_part=RealData(number_value=1),
                        measurement_unit=QudtUnit.mol_per_l,
                    ),
                ),
                SoluteComponent(
                    type=MaterialType.LithiumBisfluorosulfonylimide,
                    measured_property=MeasuredProperty(
                        type=MeasuredPropertyType.AmountConcentration,
                        numerical_part=RealData(number_value=0),
                        measurement_unit=QudtUnit.mol_per_l,
                    ),
                ),
            ],
            additive=Additive(
                type=DomainType.Additive,
                constituent=[
                    AdditiveComponent(
                        type=MaterialType.VinyleneCarbonate,
                        measured_property=MeasuredProperty(
                            type=MeasuredPropertyType.AmountConcentration,
                            numerical_part=RealData(number_value=0.16),
                            measurement_unit=QudtUnit.mol_per_l,
                        ),
                    ),
                    AdditiveComponent(
                        type=MaterialType.TrisTrimethylsilyPhosphite,
                        measured_property=MeasuredProperty(
                            type=MeasuredPropertyType.AmountConcentration,
                            numerical_part=RealData(number_value=0),
                            measurement_unit=QudtUnit.mol_per_l,
                        ),
                    ),
                ],
            ),
        ),
        measured_property=[
            MeasuredProperty(
                type=MeasuredPropertyType.ElectrolyticConductivity,
                numerical_part=RealData(number_value=8),
                measurement_unit=QudtUnit.milli_s_per_centi_m,
            ),
            MeasuredProperty(
                type=MeasuredPropertyType.DynamicViscosity,
                numerical_part=RealData(number_value=3),
                measurement_unit=QudtUnit.milli_pa_sec,
            ),
            MeasuredProperty(
                type=MeasuredPropertyType.Density,
                numerical_part=RealData(number_value=1.3),
                measurement_unit=EmmoUnit.gram_per_cubic_centi_metre,
            ),
            MeasuredProperty(
                type=MeasuredPropertyType.CelsiusTemperature,
                numerical_part=RealData(number_value=25),
                measurement_unit=EmmoUnit.celsius_temperature,
            ),
        ],
        schema_manufacturer=SchemaOrganization(
            id="https://www.wikidata.org/wiki/Q30285492",
            type=OrgName.Solvionic,
        ),
    ),
    separator=Separator(
        type=[DomainType.Separator, MaterialType.Polypropylene],
        measured_property=[
            MeasuredProperty(
                type=MeasuredPropertyType.Thickness,
                numerical_part=RealData(number_value=25),
                measurement_unit=EmmoUnit.micro_metre,
            ),
            MeasuredProperty(
                type=MeasuredPropertyType.Porosity,
                numerical_part=RealData(number_value=55),
                measurement_unit=QudtUnit.percent,
            ),
            MeasuredProperty(
                type=MeasuredPropertyType.Tortuosity,
                numerical_part=RealData(number_value=2.5),
                measurement_unit=EmmoUnit.unit_one,
            ),
            MeasuredProperty(
                type=MeasuredPropertyType.Diameter,
                numerical_part=RealData(number_value=16),
                measurement_unit=QudtUnit.milli_m,
            ),
        ],
        schema_manufacturer=SchemaOrganization(
            id="https://www.wikidata.org/wiki/Q122199856",
            type=OrgName.Celgard,
        ),
        schema_product_id=SchemaProductId(rdfs_comment=2500),
    ),
    case=Case(
        type=[MaterialType.R2032, MaterialType.StainlessSteel],
        constituent=CaseConstituents(
            cell_lid=CellLid(
                type=DomainType.CellLid,
                coating=CoatingInfo(rdfs_comment="none"),
            ),
            cell_can=CellCan(
                type=DomainType.CellCan,
                coating=CoatingInfo(type=MaterialType.Aluminium),
            ),
        ),
        schema_manufacturer=SchemaOrganization(type=OrgName.Hosen),
        schema_product_id=SchemaProductId(rdfs_comment="2032, SUS316L"),
    ),
    constituent=TopConstituents(
        spring=Spring(
            type=DomainType.Spring,
            measured_property=[
                MeasuredProperty(
                    type=MeasuredPropertyType.Diameter,
                    numerical_part=RealData(number_value=15),
                    measurement_unit=QudtUnit.milli_m,
                ),
                MeasuredProperty(
                    type=MeasuredPropertyType.Thickness,
                    numerical_part=RealData(number_value=1.4),
                    measurement_unit=QudtUnit.milli_m,
                ),
            ],
        ),
        spacer=Spacer(
            type=DomainType.Spacer,
            measured_property=[
                MeasuredProperty(
                    type=MeasuredPropertyType.Diameter,
                    numerical_part=RealData(number_value=16),
                    measurement_unit=QudtUnit.milli_m,
                ),
                MeasuredProperty(
                    type=MeasuredPropertyType.Thickness,
                    numerical_part=RealData(number_value=1),
                    measurement_unit=QudtUnit.milli_m,
                ),
            ],
        ),
    ),
)


# #print(example_coin_cell.model_dump_json(indent=2, exclude_none=True))
# json_ld = example_coin_cell.to_jsonld()
# # compact
# from pyld import jsonld

# json_ld = jsonld.compact(json_ld, BASE_CTX)

import json

# print(json.dumps(json_ld, indent=2))

# # dump it to Path(__file__).parent / "data" / "battinfo_example_min_generated.jsonld"
# from pathlib import Path
# data_path = Path(__file__).parent / "data" / "battinfo_example_min_generated.jsonld"
# with open(data_path, "w", encoding="utf-8") as f:
#     json.dump(json_ld, f, indent=2)

# # jsondiff between original and serialized
# import jsondiff

# relative path to battinfo_example_min.jsonld
data_path = Path(__file__).parent / "data" / "battinfo_example_min.jsonld"

with open(data_path, "r", encoding="utf-8") as f:
    data = json.load(f)

my_data = CoinCell.from_jsonld(data)
# print(my_data)

# json_diff = jsondiff.diff(data, json_ld, syntax='symmetric')
# print("JSON diff between original and serialized:")
# print(json_diff)

# If your LinkedBaseModel supports JSON-LD serialization:
# print(example_coin_cell.to_jsonld())

# load example data if run as script
if __name__ == "__main__":
    import json

    # # relative path to battinfo_example_min.jsonld
    # data_path = Path(__file__).parent / "data" / "battinfo_example_min.jsonld"
    # with open(data_path, "r", encoding="utf-8") as f:
    #     data = json.load(f)
    # my_data = CoinCell.from_jsonld(data)
    # print(my_data)
