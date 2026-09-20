(function () {
  'use strict';

  const INTERVALS = {
    '5': '5m',
    '15': '15m',
    '30': '30m',
    '60': '1h',
    '240': '4h',
  };

  const COLORS = {
    background: '#07101b',
    grid: '#173049',
    text: '#8195a9',
    up: '#36d39a',
    down: '#ff6b6b',
    entry: '#62a8ff',
    tp1: '#35e0b2',
    tp2: '#b5df48',
    tp3: '#a979ff',
    stop: '#ff4f62',
    current: '#4dd9ff',
  };

  function number(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function formatPrice(value) {
    const parsed = number(value);
    if (parsed === null) return '—';
    const decimals = parsed >= 1000 ? 2 : parsed >= 1 ? 3 : 6;
    return parsed.toLocaleString('es-AR', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  }

  class PaperTradeChart {
    constructor(containerId, canvasId) {
      this.container = document.getElementById(containerId);
      this.canvas = document.getElementById(canvasId);
      this.context = this.canvas ? this.canvas.getContext('2d') : null;
      this.status = this.container?.querySelector('[data-chart-status]') || null;
      this.symbol = '';
      this.interval = '';
      this.candles = [];
      this.plan = null;
      this.socket = null;
      this.requestId = 0;
      this.reconnectTimer = null;
      this.resizeObserver = null;

      if (this.container && this.canvas && this.context) {
        this.resizeObserver = new ResizeObserver(() => this.draw());
        this.resizeObserver.observe(this.container);
      }
    }

    setPlan(plan) {
      this.plan = plan || null;
      this.draw();
    }

    async render(symbol, interval, plan) {
      symbol = String(symbol || 'ETHUSDT').replace('/', '').toUpperCase();
      if (!['BTCUSDT', 'ETHUSDT'].includes(symbol)) symbol = 'ETHUSDT';
      interval = INTERVALS[String(interval)] || '15m';
      this.plan = plan || null;

      if (this.symbol === symbol && this.interval === interval && this.candles.length) {
        this.draw();
        return;
      }

      this.symbol = symbol;
      this.interval = interval;
      this.candles = [];
      this.requestId += 1;
      const requestId = this.requestId;
      this.closeSocket();
      this.setStatus('Cargando velas públicas de Binance…');
      this.draw();

      try {
        const url = 'https://api.binance.com/api/v3/klines?symbol='
          + encodeURIComponent(symbol)
          + '&interval=' + encodeURIComponent(interval)
          + '&limit=120';
        const response = await fetch(url, { cache: 'no-store' });
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const rows = await response.json();
        if (requestId !== this.requestId) return;
        this.candles = rows.map(row => ({
          time: Number(row[0]),
          open: Number(row[1]),
          high: Number(row[2]),
          low: Number(row[3]),
          close: Number(row[4]),
        })).filter(candle => Object.values(candle).every(Number.isFinite));
        this.setStatus('● EN VIVO · Binance · ' + symbol.replace('USDT', '/USDT') + ' · ' + interval);
        this.connectSocket();
        this.draw();
      } catch (error) {
        if (requestId !== this.requestId) return;
        this.setStatus('No se pudieron cargar las velas · reintentá en unos segundos', true);
        this.draw();
      }
    }

    setStatus(message, error) {
      if (!this.status) return;
      this.status.textContent = message;
      this.status.className = 'paper-chart-status' + (error ? ' error' : '');
    }

    closeSocket() {
      clearTimeout(this.reconnectTimer);
      if (this.socket) {
        this.socket.onclose = null;
        this.socket.close();
        this.socket = null;
      }
    }

    connectSocket() {
      this.closeSocket();
      const stream = this.symbol.toLowerCase() + '@kline_' + this.interval;
      this.socket = new WebSocket('wss://stream.binance.com:9443/ws/' + stream);
      this.socket.onmessage = event => {
        const payload = JSON.parse(event.data);
        const row = payload.k;
        if (!row) return;
        const candle = {
          time: Number(row.t),
          open: Number(row.o),
          high: Number(row.h),
          low: Number(row.l),
          close: Number(row.c),
        };
        if (!Object.values(candle).every(Number.isFinite)) return;
        const last = this.candles[this.candles.length - 1];
        if (last && last.time === candle.time) this.candles[this.candles.length - 1] = candle;
        else {
          this.candles.push(candle);
          if (this.candles.length > 120) this.candles.shift();
        }
        this.draw();
      };
      this.socket.onclose = () => {
        this.reconnectTimer = setTimeout(() => this.connectSocket(), 3000);
      };
    }

    resizeCanvas() {
      if (!this.canvas || !this.container) return null;
      const width = Math.max(320, this.container.clientWidth);
      const height = Math.max(360, this.container.clientHeight);
      const ratio = window.devicePixelRatio || 1;
      if (this.canvas.width !== Math.floor(width * ratio)
        || this.canvas.height !== Math.floor(height * ratio)) {
        this.canvas.width = Math.floor(width * ratio);
        this.canvas.height = Math.floor(height * ratio);
        this.canvas.style.width = width + 'px';
        this.canvas.style.height = height + 'px';
      }
      this.context.setTransform(ratio, 0, 0, ratio, 0, 0);
      return { width, height };
    }

    draw() {
      if (!this.context) return;
      const size = this.resizeCanvas();
      if (!size) return;
      const ctx = this.context;
      const { width, height } = size;
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = COLORS.background;
      ctx.fillRect(0, 0, width, height);

      if (!this.candles.length) {
        ctx.fillStyle = COLORS.text;
        ctx.font = '13px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Esperando velas…', width / 2, height / 2);
        return;
      }

      const padding = { top: 22, right: 92, bottom: 32, left: 12 };
      const plotWidth = width - padding.left - padding.right;
      const plotHeight = height - padding.top - padding.bottom;
      const planPrices = this.plan
        ? [this.plan.entry, this.plan.stop, ...(this.plan.targets || []).map(target => target.price)]
            .map(number).filter(value => value !== null)
        : [];
      const candlePrices = this.candles.flatMap(candle => [candle.high, candle.low]);
      let minPrice = Math.min(...candlePrices, ...planPrices);
      let maxPrice = Math.max(...candlePrices, ...planPrices);
      const paddingPrice = Math.max((maxPrice - minPrice) * 0.08, maxPrice * 0.0005);
      minPrice -= paddingPrice;
      maxPrice += paddingPrice;
      const priceRange = Math.max(maxPrice - minPrice, 0.00000001);
      const y = price => padding.top + (maxPrice - price) / priceRange * plotHeight;

      ctx.lineWidth = 1;
      ctx.font = '10px Arial';
      for (let index = 0; index <= 5; index += 1) {
        const lineY = padding.top + plotHeight * index / 5;
        const price = maxPrice - priceRange * index / 5;
        ctx.strokeStyle = COLORS.grid;
        ctx.beginPath();
        ctx.moveTo(padding.left, lineY);
        ctx.lineTo(padding.left + plotWidth, lineY);
        ctx.stroke();
        ctx.fillStyle = COLORS.text;
        ctx.textAlign = 'left';
        ctx.fillText(formatPrice(price), width - padding.right + 8, lineY + 3);
      }

      this.drawPlan(ctx, y, padding, plotWidth, width);

      const slot = plotWidth / this.candles.length;
      const candleWidth = Math.max(2, Math.min(8, slot * 0.62));
      this.candles.forEach((candle, index) => {
        const x = padding.left + slot * index + slot / 2;
        const rising = candle.close >= candle.open;
        const color = rising ? COLORS.up : COLORS.down;
        ctx.strokeStyle = color;
        ctx.beginPath();
        ctx.moveTo(x, y(candle.high));
        ctx.lineTo(x, y(candle.low));
        ctx.stroke();
        ctx.fillStyle = color;
        const top = y(Math.max(candle.open, candle.close));
        const bottom = y(Math.min(candle.open, candle.close));
        ctx.fillRect(x - candleWidth / 2, top, candleWidth, Math.max(1.5, bottom - top));
      });

      const latest = this.candles[this.candles.length - 1];
      const currentY = y(latest.close);
      ctx.save();
      ctx.setLineDash([3, 4]);
      ctx.strokeStyle = COLORS.current;
      ctx.beginPath();
      ctx.moveTo(padding.left, currentY);
      ctx.lineTo(padding.left + plotWidth, currentY);
      ctx.stroke();
      ctx.restore();

      ctx.fillStyle = COLORS.text;
      ctx.textAlign = 'left';
      const firstTime = new Date(this.candles[0].time);
      const lastTime = new Date(latest.time);
      ctx.fillText(firstTime.toLocaleString('es-AR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }), padding.left, height - 10);
      ctx.textAlign = 'right';
      ctx.fillText(lastTime.toLocaleString('es-AR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }), padding.left + plotWidth, height - 10);
    }

    drawPlan(ctx, y, padding, plotWidth, width) {
      if (!this.plan) return;
      const entry = number(this.plan.entry);
      const stop = number(this.plan.stop);
      const targets = (this.plan.targets || [])
        .map(target => ({ ...target, price: number(target.price) }))
        .filter(target => target.price !== null);
      if (entry === null || stop === null || !targets.length) return;

      const zoneStart = padding.left + plotWidth * 0.53;
      const zoneEnd = padding.left + plotWidth;
      const current = number(this.candles[this.candles.length - 1]?.close);
      const direction = String(this.plan.direction || 'LONG').toUpperCase();
      const reached = price => this.plan.status === 'PENDING'
        ? false
        : direction === 'LONG' ? current >= price : current <= price;

      const fillBetween = (first, second, color, alpha) => {
        const top = Math.min(y(first), y(second));
        const zoneHeight = Math.max(1, Math.abs(y(first) - y(second)));
        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.fillStyle = color;
        ctx.fillRect(zoneStart, top, zoneEnd - zoneStart, zoneHeight);
        ctx.restore();
      };

      fillBetween(entry, stop, COLORS.stop, 0.20);
      let previous = entry;
      targets.forEach((target, index) => {
        fillBetween(previous, target.price, [COLORS.tp1, COLORS.tp2, COLORS.tp3][index] || COLORS.tp3, 0.13 + index * 0.025);
        previous = target.price;
      });

      const levels = [
        { name: 'SL', price: stop, color: COLORS.stop, hit: false },
        { name: 'ENTRY', price: entry, color: COLORS.entry, hit: false },
        ...targets.map((target, index) => ({
          name: target.name || ('TP' + (index + 1)),
          price: target.price,
          color: [COLORS.tp1, COLORS.tp2, COLORS.tp3][index] || COLORS.tp3,
          hit: Boolean(target.hit_at) || reached(target.price),
        })),
      ];

      levels.forEach(level => {
        const lineY = y(level.price);
        ctx.save();
        ctx.setLineDash(level.name === 'ENTRY' ? [] : [6, 5]);
        ctx.strokeStyle = level.color;
        ctx.lineWidth = level.name === 'ENTRY' ? 1.6 : 1;
        ctx.beginPath();
        ctx.moveTo(zoneStart, lineY);
        ctx.lineTo(zoneEnd, lineY);
        ctx.stroke();
        ctx.restore();

        const label = (level.hit ? '✓ ' : '') + level.name + ' ' + formatPrice(level.price);
        ctx.font = 'bold 10px Arial';
        const labelWidth = Math.min(88, Math.max(58, ctx.measureText(label).width + 10));
        const labelX = Math.min(width - labelWidth - 2, zoneEnd - labelWidth + 1);
        ctx.fillStyle = level.color;
        ctx.fillRect(labelX, lineY - 10, labelWidth, 19);
        ctx.fillStyle = '#06101a';
        ctx.textAlign = 'left';
        ctx.fillText(label, labelX + 5, lineY + 3);
      });

      const markerY = y(entry);
      ctx.fillStyle = direction === 'LONG' ? COLORS.up : COLORS.down;
      ctx.beginPath();
      if (direction === 'LONG') {
        ctx.moveTo(zoneStart - 12, markerY + 9);
        ctx.lineTo(zoneStart - 3, markerY - 7);
        ctx.lineTo(zoneStart + 6, markerY + 9);
      } else {
        ctx.moveTo(zoneStart - 12, markerY - 9);
        ctx.lineTo(zoneStart - 3, markerY + 7);
        ctx.lineTo(zoneStart + 6, markerY - 9);
      }
      ctx.closePath();
      ctx.fill();
    }
  }

  window.ProjectEdgePaperChart = PaperTradeChart;
})();
