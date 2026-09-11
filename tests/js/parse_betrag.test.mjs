// QA2-02: Regressionstest fuer parseBetrag() aus static-neu/format.js.
// Wird per `node tests/js/parse_betrag.test.mjs` ausgefuehrt (Exit-Code != 0 bei Fehlschlag).
// Aufruf aus Python: siehe tests/test_qa2_02_parse_betrag.py (subprocess.run(["node", ...])).

import { parseBetrag } from '../../static-neu/format.js';

const faelle = [
  ['12,50', 12.5],
  ['12.50', 12.5],
  ['1.250', 1250],
  ['1.250,00', 1250],
  ['1,250.00', 1250],
  ['12.5', 12.5],
  ['1250', 1250],
  ['abc', null],
];

let fehler = 0;
for (const [eingabe, erwartet] of faelle) {
  const ergebnis = parseBetrag(eingabe);
  if (ergebnis !== erwartet) {
    fehler++;
    console.error(`FEHLER: parseBetrag(${JSON.stringify(eingabe)}) = ${ergebnis}, erwartet ${erwartet}`);
  }
}

if (fehler > 0) {
  console.error(`${fehler} von ${faelle.length} Faellen fehlgeschlagen.`);
  process.exit(1);
}
console.log(`Alle ${faelle.length} parseBetrag-Faelle bestanden.`);
