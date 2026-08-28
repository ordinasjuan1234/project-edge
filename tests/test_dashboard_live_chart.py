from pathlib import Path


HTML = (Path(__file__).resolve().parents[1] / "index.html").read_text(encoding="utf-8")


def test_manual_dashboard_embeds_official_tradingview_chart():
    assert 'id="manualTradingViewChart"' in HTML
    assert "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" in HTML
    assert "symbol:'BINANCE:'+symbol" in HTML
    assert "allow_symbol_change:false" in HTML


def test_live_chart_is_restricted_to_manual_paper_assets():
    assert "['BTCUSDT','ETHUSDT'].includes(symbol)" in HTML
    assert "todos los controles continúan exclusivamente en PAPER / DEMO" in HTML
    assert "no abre ni cierra operaciones" in HTML


def test_live_chart_exposes_requested_timeframes():
    for value, label in (
        ("5", "5 minutos"),
        ("15", "15 minutos"),
        ("30", "30 minutos"),
        ("60", "1 hora"),
        ("240", "4 horas"),
    ):
        assert f'<option value="{value}"' in HTML
        assert label in HTML


def test_live_chart_follows_manual_symbol_and_open_position():
    assert "renderManualTradingViewChart(liveTargetSymbol)" in HTML
    assert "renderManualTradingViewChart(symbol)" in HTML
    assert "renderManualTradingViewChart(manualChartTargetSymbol)" in HTML


def test_live_chart_shows_only_confirmed_project_edge_signal():
    assert 'id=\'manualChartSignal\'' in HTML
    assert "ALCISTA · COMPRAR · LONG" in HTML
    assert "BAJISTA · VENDER · SHORT" in HTML
    assert "SIN CONFIRMACIÓN · ESPERAR" in HTML
    assert "Señal técnica PAPER confirmada por PROJECT EDGE" in HTML


def test_live_chart_prioritizes_open_paper_position():
    assert "POSICIÓN PAPER · LONG" in HTML
    assert "POSICIÓN PAPER · SHORT" in HTML
    assert "Entrada '+fmt(position.entry_price)+' USDT" in HTML


def test_live_chart_identifies_pending_limit_order():
    assert "ORDEN LIMIT PAPER · LONG" in HTML
    assert "ORDEN LIMIT PAPER · SHORT" in HTML
    assert "Esperando ejecución en '+fmt(pending.limit_price)+' USDT" in HTML
