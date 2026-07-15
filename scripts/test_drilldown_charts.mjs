import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const source = fs.readFileSync(new URL("../static-studio/charts.js", import.meta.url), "utf8");
const context = { console, isFinite, Intl };
vm.createContext(context);
vm.runInContext(source + "\nglobalThis.__Charts = Charts;", context);
const Charts = context.__Charts;

function fakeElement() {
  const listeners = {};
  return {
    innerHTML: "",
    addEventListener(type, callback) { listeners[type] = callback; },
    click(dataset, selector) {
      assert.ok(listeners.click, "Chart muss einen delegierten click-Handler registrieren");
      listeners.click({ target: { closest: (requested) => requested === selector ? { dataset } : null } });
    },
  };
}

{
  const el = fakeElement();
  let clicked = null;
  Charts.barGroup(el, {
    labels: ["Jul 26"],
    series: [{ name: "Ausgaben", color: "red", values: [1234] }],
    onBarClick(label, seriesName) { clicked = { label, seriesName }; },
  });
  assert.match(el.innerHTML, /data-bar-index="0"/);
  assert.match(el.innerHTML, /cursor:pointer/);
  el.click({ barIndex: "0", seriesIndex: "0" }, "rect[data-bar-index]");
  assert.deepEqual(clicked, { label: "Jul 26", seriesName: "Ausgaben" });
}

{
  const el = fakeElement();
  const row = { label: "Versicherung", kategorie_id: 42, value: 5000 };
  let clicked = null;
  Charts.rankList(el, [row], { onRowClick(value) { clicked = value; } });
  assert.match(el.innerHTML, /data-row-index="0"/);
  assert.match(el.innerHTML, /cursor:pointer/);
  el.click({ rowIndex: "0" }, ".rank-row[data-row-index]");
  assert.equal(clicked, row, "Callback muss das unveraenderte Row-Objekt erhalten");
}

console.log("Chart-Drilldown-Callbacks: 2/2 bestanden");
