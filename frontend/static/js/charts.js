import { fmt } from './utils.js';

const COLORS = [
  '#7c6cff',
  '#ff6c6c',
  '#6cffb4',
  '#ffb86c',
  '#6cb4ff',
  '#ff6cde',
  '#6cfff4',
  '#ffd96c',
  '#c46cff',
  '#6cff8a',
];

let chartMonthly;
let chartCats;
let chartBar;
let chartWeekday;

export function destroyCharts() {
  if (chartMonthly) chartMonthly.destroy();
  if (chartCats) chartCats.destroy();
  if (chartBar) chartBar.destroy();
  if (chartWeekday) chartWeekday.destroy();
  chartMonthly = chartCats = chartBar = chartWeekday = null;
}

export function buildCharts(transactions) {
  const expenses = transactions.filter((t) => t.amount_uah < 0);
  const totalExp = expenses.reduce((s, t) => s + Math.abs(t.amount_uah), 0);
  const months = [...new Set(transactions.map((t) => t.date.slice(0, 7)))].sort();

  const monthlyData = {};
  months.forEach((m) => {
    monthlyData[m] = 0;
  });
  expenses.forEach((t) => {
    const m = t.date.slice(0, 7);
    if (monthlyData[m] !== undefined) monthlyData[m] += Math.abs(t.amount_uah);
  });

  if (chartMonthly) chartMonthly.destroy();
  chartMonthly = new Chart(document.getElementById('chartMonthly'), {
    type: 'bar',
    data: {
      labels: months.map((m) => {
        const [y, mo] = m.split('-');
        return (
          ['', 'Січ', 'Лют', 'Бер', 'Кві', 'Тра', 'Чер', 'Лип', 'Сер', 'Вер', 'Жов', 'Лис', 'Гру'][+mo] +
          ' ' +
          y.slice(2)
        );
      }),
      datasets: [
        {
          label: 'UAH',
          data: months.map((m) => Math.round(monthlyData[m])),
          backgroundColor: months.map((_, i) =>
            i === months.length - 1 ? '#7c6cff' : 'rgba(124,108,255,0.35)',
          ),
          borderRadius: 5,
          borderSkipped: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: { color: '#6b6b80', font: { family: 'DM Mono', size: 10 } },
        },
        y: {
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: {
            color: '#6b6b80',
            font: { family: 'DM Mono', size: 10 },
            callback: (v) => fmt(v) + '₴',
          },
        },
      },
    },
  });

  const catSums = {};
  expenses.forEach((t) => {
    const c = t.category || 'Інше';
    catSums[c] = (catSums[c] || 0) + Math.abs(t.amount_uah);
  });
  const sortedCats = Object.entries(catSums).sort((a, b) => b[1] - a[1]);
  const top8 = sortedCats.slice(0, 8);
  const otherSum = sortedCats.slice(8).reduce((s, [, v]) => s + v, 0);
  if (otherSum > 0) top8.push(['Інше', otherSum]);

  if (chartCats) chartCats.destroy();
  chartCats = new Chart(document.getElementById('chartCats'), {
    type: 'doughnut',
    data: {
      labels: top8.map(([c]) => c),
      datasets: [
        {
          data: top8.map(([, v]) => Math.round(v)),
          backgroundColor: COLORS,
          borderWidth: 0,
          hoverOffset: 5,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '62%',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) =>
              ` ${fmt(ctx.raw)} UAH (${((ctx.raw / totalExp) * 100).toFixed(1)}%)`,
          },
        },
      },
    },
  });

  const top10 = sortedCats.slice(0, 10);
  document.getElementById('barChartWrap').style.height = top10.length * 38 + 40 + 'px';
  if (chartBar) chartBar.destroy();
  chartBar = new Chart(document.getElementById('chartBar'), {
    type: 'bar',
    data: {
      labels: top10.map(([c]) => (c.length > 20 ? c.slice(0, 18) + '…' : c)),
      datasets: [
        {
          data: top10.map(([, v]) => Math.round(v)),
          backgroundColor: COLORS,
          borderRadius: 4,
          borderSkipped: false,
        },
      ],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: {
            color: '#6b6b80',
            font: { family: 'DM Mono', size: 10 },
            callback: (v) => fmt(v) + '₴',
          },
        },
        y: {
          grid: { display: false },
          ticks: { color: '#c0c0d0', font: { family: 'Syne', size: 11 } },
        },
      },
    },
  });

  const wTotals = [0, 0, 0, 0, 0, 0, 0];
  const wCounts = [0, 0, 0, 0, 0, 0, 0];
  expenses.forEach((t) => {
    const d = new Date(t.date).getDay();
    wTotals[d] += Math.abs(t.amount_uah);
    wCounts[d]++;
  });
  const wAvg = wTotals.map((v, i) => (wCounts[i] ? Math.round(v / wCounts[i]) : 0));
  if (chartWeekday) chartWeekday.destroy();
  chartWeekday = new Chart(document.getElementById('chartWeekday'), {
    type: 'radar',
    data: {
      labels: ['Нд', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'],
      datasets: [
        {
          data: wAvg,
          backgroundColor: 'rgba(124,108,255,0.15)',
          borderColor: '#7c6cff',
          borderWidth: 1.5,
          pointBackgroundColor: '#7c6cff',
          pointRadius: 3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        r: {
          grid: { color: 'rgba(255,255,255,0.06)' },
          angleLines: { color: 'rgba(255,255,255,0.06)' },
          ticks: { display: false },
          pointLabels: { color: '#6b6b80', font: { family: 'DM Mono', size: 10 } },
        },
      },
    },
  });
}
