"""Physical-unit helpers for goods master data and transaction totals."""

from decimal import Decimal, InvalidOperation


INCH_TO_METER = Decimal('0.0254')
CM_TO_METER = Decimal('0.01')
MM_TO_METER = Decimal('0.001')
LB_TO_KG = Decimal('0.45359237')
KG_TO_LB = Decimal('2.20462262185')


def _number(value):
    if value in (None, ''):
        return Decimal('0')
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0')


def numeric_value(value):
    return float(_number(value))


def _unit_text(unit):
    return str(unit or '').strip().lower().replace(' ', '')


def dimension_factor_to_meters(measurement_unit):
    unit = _unit_text(measurement_unit)
    if 'in' in unit:
        return INCH_TO_METER
    if 'cm' in unit:
        return CM_TO_METER
    if 'mm' in unit:
        return MM_TO_METER
    # Existing records predate measurement_unit and use mm/g internally.
    return MM_TO_METER


def unit_volume_cubic_meters(width, depth, height, measurement_unit=''):
    factor = dimension_factor_to_meters(measurement_unit)
    volume = _number(width) * _number(depth) * _number(height) * factor ** 3
    return float(volume.quantize(Decimal('0.0001')))


def weight_to_kg(weight, measurement_unit=''):
    if hasattr(weight, 'goods_weight'):
        measurement_unit = getattr(weight, 'measurement_unit', measurement_unit)
        weight = getattr(weight, 'goods_weight', 0)
    unit = _unit_text(measurement_unit)
    value = _number(weight)
    if 'lb' in unit:
        return float((value * LB_TO_KG).quantize(Decimal('0.0001')))
    if 'kg' in unit:
        return float(value.quantize(Decimal('0.0001')))
    if 'oz' in unit:
        return float((value * Decimal('0.028349523125')).quantize(Decimal('0.0001')))
    # Existing records predate measurement_unit and store grams.
    return float((value / Decimal('1000')).quantize(Decimal('0.0001')))


def source_value_to_us(value, unit, kind):
    """Return a converted value and normalized US unit for source imports."""
    raw = _number(value)
    source = _unit_text(unit)
    if kind == 'dimension':
        if 'cm' in source:
            return float((raw / Decimal('2.54')).quantize(Decimal('0.0001'))), 'in'
        if 'mm' in source:
            return float((raw / Decimal('25.4')).quantize(Decimal('0.0001'))), 'in'
        return float(raw), 'in'
    if kind == 'weight':
        if 'kg' in source:
            return float((raw * KG_TO_LB).quantize(Decimal('0.0001'))), 'lb'
        if 'g' in source and 'kg' not in source:
            return float((raw * KG_TO_LB / Decimal('1000')).quantize(Decimal('0.0001'))), 'lb'
        if 'oz' in source:
            return float((raw / Decimal('16')).quantize(Decimal('0.0001'))), 'lb'
        return float(raw), 'lb'
    raise ValueError(f'Unsupported source conversion kind: {kind}')
