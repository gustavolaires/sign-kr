// Dashboard: instancia os gráficos (Chart.js) a partir dos dados serializados
// pelo backend em #dashboard-data. Todos os valores já vêm em reais; a matemática
// (agregações, metas) é feita no serviço sign.services.dashboard_metrics.
(function () {
  "use strict";

  if (typeof Chart === "undefined") return;

  var dataEl = document.getElementById("dashboard-data");
  if (!dataEl) return;
  var data = JSON.parse(dataEl.textContent);

  // Paleta triádica pop-art (ver cores.png): azul + amarelo-ouro + vermelho.
  var BLUE = "#155AF0"; // azul principal (ok / pago / faturamento / atingido)
  var YELLOW = "#F6B717"; // amarelo-ouro (atenção / pendente / meta)
  var RED = "#E42D28"; // vermelho (crítico / zerado)
  var TRACK = "#e5e7eb"; // gray-200 (trilho dos medidores)
  var SURFACE = "#ffffff";

  Chart.defaults.font.family =
    "system-ui, -apple-system, 'Segoe UI', sans-serif";
  Chart.defaults.color = "#52514e";

  function brl(value) {
    return "R$ " + (value || 0).toFixed(2).replace(".", ",");
  }

  // ---- Combo de faturamento por dia: barras + linha de meta diária ----
  // Reaproveitado pelas séries "semana por dia" e "mês por dia".
  function salesByDayChart(canvasId, series) {
    var canvas = document.getElementById(canvasId);
    if (!canvas) return;
    var s = series || {};
    var dailyGoal = s.daily_goal || 0;
    var goalLine = (s.labels || []).map(function () {
      return dailyGoal;
    });
    new Chart(canvas, {
      data: {
        labels: s.labels || [],
        datasets: [
          {
            type: "bar",
            label: "Faturamento",
            data: s.revenue || [],
            backgroundColor: BLUE,
            borderRadius: 4,
            borderSkipped: false,
            order: 2,
          },
          {
            type: "line",
            label: "Meta diária",
            data: goalLine,
            borderColor: YELLOW,
            borderWidth: 2,
            borderDash: [6, 4],
            pointRadius: 0,
            fill: false,
            order: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            ticks: { callback: brl },
            grid: { color: "#e1e0d9" },
          },
          x: { grid: { display: false } },
        },
        plugins: {
          legend: { position: "bottom" },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                return ctx.dataset.label + ": " + brl(ctx.parsed.y);
              },
              afterLabel: function (ctx) {
                if (ctx.dataset.type !== "bar" || !dailyGoal) return "";
                var pct = (ctx.parsed.y / dailyGoal) * 100;
                return pct.toFixed(1) + "% da meta diária";
              },
            },
          },
        },
      },
    });
  }

  salesByDayChart("chart-weekly", data.weekly);
  salesByDayChart("chart-monthly", data.monthly);

  // ---- Medidor (gauge) de meta: atingido vs. restante ----
  function gauge(canvasId, labelId, goalData) {
    var canvas = document.getElementById(canvasId);
    if (!canvas) return;
    var attained = goalData.attained || 0;
    var goal = goalData.goal || 0;
    var remaining = Math.max(0, goal - attained);
    var labelEl = document.getElementById(labelId);
    if (labelEl) {
      labelEl.textContent = goalData.pct === null ? "—" : goalData.pct + "%";
    }
    new Chart(canvas, {
      type: "doughnut",
      data: {
        labels: ["Atingido", "Restante"],
        datasets: [
          {
            data: goal ? [attained, remaining] : [0, 1],
            backgroundColor: goal ? [BLUE, TRACK] : [TRACK, TRACK],
            borderColor: SURFACE,
            borderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "75%",
        plugins: {
          legend: { display: false },
          tooltip: {
            enabled: !!goal,
            callbacks: {
              label: function (ctx) {
                return ctx.label + ": " + brl(ctx.parsed);
              },
            },
          },
        },
      },
    });
  }

  gauge("chart-week-goal", "week-goal-pct", data.week_goal || {});
  gauge("chart-month-goal", "month-goal-pct", data.month_goal || {});

  // ---- Doughnut de estado (com legenda + rótulos) ----
  // legendFormatter (opcional): quando informado, anexa o valor formatado ao
  // rótulo de cada item da legenda, deixando os valores sempre visíveis.
  function statusDoughnut(canvasId, labels, values, colors, formatter, legendFormatter) {
    var canvas = document.getElementById(canvasId);
    if (!canvas) return;
    var legend = { position: "bottom" };
    if (legendFormatter) {
      legend.labels = {
        generateLabels: function (chart) {
          var ds = chart.data.datasets[0];
          return chart.data.labels.map(function (label, i) {
            return {
              text: label + ": " + legendFormatter(ds.data[i]),
              fillStyle: ds.backgroundColor[i],
              strokeStyle: SURFACE,
              lineWidth: 2,
              index: i,
            };
          });
        },
      };
    }
    new Chart(canvas, {
      type: "doughnut",
      data: {
        labels: labels,
        datasets: [
          {
            data: values,
            backgroundColor: colors,
            borderColor: SURFACE,
            borderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "60%",
        plugins: {
          legend: legend,
          tooltip: {
            callbacks: {
              label: function (ctx) {
                return ctx.label + ": " + formatter(ctx.parsed);
              },
            },
          },
        },
      },
    });
  }

  var stock = data.stock || {};
  statusDoughnut(
    "chart-stock",
    ["Ok", "Estoque baixo", "Estoque zerado"],
    [stock.ok || 0, stock.low || 0, stock.zero || 0],
    [BLUE, YELLOW, RED],
    function (v) {
      return v + " produto(s)";
    }
  );

  var expenses = data.expenses || {};
  statusDoughnut(
    "chart-expenses",
    ["Pagas", "Pendentes"],
    [expenses.paid || 0, expenses.unpaid || 0],
    [BLUE, YELLOW],
    brl
  );

  // ---- Doughnut de formas de pagamento (valor por tipo) ----
  // Paleta categórica por código de pagamento (tokens da marca + cinza).
  var PAYMENT_COLORS = {
    credit: BLUE,
    debit: "#1b2a4e", // navy
    cash: YELLOW,
    pix: RED,
    other: "#9ca3af", // gray-400
  };

  function paymentDoughnut(canvasId, items) {
    items = items || [];
    if (!items.length) {
      // Estado vazio: anel cinza único, sem tooltip.
      statusDoughnut(
        canvasId,
        ["Sem vendas no período"],
        [1],
        [TRACK],
        function () {
          return "";
        }
      );
      return;
    }
    statusDoughnut(
      canvasId,
      items.map(function (i) {
        return i.label;
      }),
      items.map(function (i) {
        return i.value;
      }),
      items.map(function (i) {
        return PAYMENT_COLORS[i.code] || "#9ca3af";
      }),
      brl,
      brl // valores visíveis na legenda (ex.: "Dinheiro: R$ 150,00")
    );
  }

  paymentDoughnut("chart-payments-today", data.payments_today);
  paymentDoughnut("chart-payments-week", data.payments_week);
})();
