"""Tests for horario slot resolution."""

from app.services.horario_resolver import resolver_horario


def test_resolver_ordinal_ti():
    st, et = resolver_horario("1º Horário", "EM 1 TI", "Integral")
    assert st is not None and et is not None
    assert st.strftime("%H:%M") == "07:30"
    assert et.strftime("%H:%M") == "08:30"


def test_resolver_faixa_string():
    st, et = resolver_horario("07:30 às 08:30", "EM 1 TI", "Integral")
    assert st.strftime("%H:%M") == "07:30"
    assert et.strftime("%H:%M") == "08:30"
