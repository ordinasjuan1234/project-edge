from pathlib import Path


HTML = (Path(__file__).resolve().parents[1] / "index.html").read_text(encoding="utf-8")


def test_dashboard_embeds_two_official_tradingview_charts():
    assert 'id="autoTradingViewChart"' in HTML
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


def test_auto_and_manual_charts_have_independent_targets():
    assert 'id="autoChartSymbolLabel">ETH/USDT' in HTML
    assert 'id="manualChartSymbol"' in HTML
    assert "renderAutoTradingViewChart(autoTargetSymbol)" in HTML
    assert "renderManualTradingViewChart(symbol)" in HTML
    assert "renderManualTradingViewChart(manualChartSelector?.value||'BTC/USDT')" in HTML
    assert "chartSelector.value=e.target.value" in HTML


def test_both_charts_render_when_operations_tab_opens():
    assert "renderAutoTradingViewChart(autoChartTargetSymbol)" in HTML
    assert "renderManualTradingViewChart(manualChartTargetSymbol)" in HTML
    assert "mountTradingViewChart(chart,symbol,interval)" in HTML


def test_auto_chart_follows_only_auto_state_and_engine_symbol():
    assert "String(position.source||'').toUpperCase()==='AUTO'" in HTML
    assert "String(pending.source||'').toUpperCase()==='AUTO'" in HTML
    assert "autoPosition?pos.symbol:autoPending?pending.symbol:(d.symbol||'ETHUSDT')" in HTML
    assert "AUTO PAPER · POSICIÓN LONG" in HTML
    assert "AUTO PAPER · POSICIÓN SHORT" in HTML


def test_manual_chart_prioritizes_only_manual_state():
    assert "String(position.source||'').toUpperCase()==='MANUAL'" in HTML
    assert "String(pending.source||'').toUpperCase()==='MANUAL'" in HTML
    assert "manualPosition?pos.symbol:pending.symbol" in HTML


def test_live_chart_shows_only_confirmed_project_edge_signal():
    assert 'id="manualChartSignal"' in HTML
    assert "ALCISTA · COMPRAR · LONG" in HTML
    assert "BAJISTA · VENDER · SHORT" in HTML
    assert "SIN CONFIRMACIÓN · ESPERAR" in HTML
    assert "Señal técnica PAPER confirmada por PROJECT EDGE" in HTML


def test_auto_chart_requires_executable_engine_confirmation():
    assert "canExecute=d.decision?.can_execute===true" in HTML
    assert "canExecute&&action.includes('LONG')" in HTML
    assert "canExecute&&action.includes('SHORT')" in HTML
    assert "AUTO · SIN CONFIRMACIÓN · ESPERAR" in HTML
    assert "Oportunidad AUTO PAPER confirmada por PROJECT EDGE" in HTML


def test_live_chart_prioritizes_open_paper_position():
    assert "POSICIÓN PAPER · LONG" in HTML
    assert "POSICIÓN PAPER · SHORT" in HTML
    assert "Entrada '+fmt(position.entry_price)+' USDT" in HTML


def test_live_chart_identifies_pending_limit_order():
    assert "ORDEN LIMIT PAPER · LONG" in HTML
    assert "ORDEN LIMIT PAPER · SHORT" in HTML
    assert "Esperando ejecución en '+fmt(pending.limit_price)+' USDT" in HTML


def test_chart_status_bars_stay_outside_the_candle_area():
    assert 'id="autoChartSignal"' in HTML
    assert 'id="manualChartSignal"' in HTML
    assert HTML.index('id="autoChartSignal"') < HTML.index(
        'id="autoTradingViewChart"'
    )
    assert HTML.index('id="manualChartSignal"') < HTML.index(
        'id="manualTradingViewChart"'
    )
    assert ".chart-signal{display:flex" in HTML
    assert "position:absolute" not in HTML
    assert "chart.appendChild(signal)" not in HTML
