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

  // ---- Combo semanal: barras (faturamento/dia) + linha de meta diária ----
  var weekly = data.weekly || {};
  var weeklyCanvas = document.getElementById("chart-weekly");
  if (weeklyCanvas) {
    var dailyGoal = weekly.daily_goal || 0;
    var goalLine = (weekly.labels || []).map(function () {
      return dailyGoal;
    });
    new Chart(weeklyCanvas, {
      data: {
        labels: weekly.labels || [],
        datasets: [
          {
            type: "bar",
            label: "Faturamento",
            data: weekly.revenue || [],
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
  function statusDoughnut(canvasId, labels, values, colors, formatter) {
    var canvas = document.getElementById(canvasId);
    if (!canvas) return;
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
          legend: { position: "bottom" },
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
})();
