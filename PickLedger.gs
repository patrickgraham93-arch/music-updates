/**
 * Pick Ledger Builder — container-bound Google Apps Script
 * Entry point: buildPickLedger()
 *
 * Discovers the Future Picks grid structure at runtime (no hardcoded
 * cell coordinates). Produces a Team Map tab and a Pick Ledger tab.
 * Run from the Apps Script editor — no clasp or deployment needed.
 */

// ═══════════════════════════════════════════════════════════════════════
//  CONFIG — confirm / edit before running
// ═══════════════════════════════════════════════════════════════════════
var CONFIG = {
  SOURCE_TAB:   'Future Picks',  // tab that holds the existing pick grid
  LEDGER_TAB:   'Pick Ledger',   // output: one row per pick
  TEAM_MAP_TAB: 'Team Map',      // output: code → full name reference
};

// ═══════════════════════════════════════════════════════════════════════
//  TEAM REFERENCE DATA
// ═══════════════════════════════════════════════════════════════════════
// 14 active teams — diacritics preserved exactly as requested
var ACTIVE_TEAMS = [
  ['BK', 'Brian Kardane'],
  ['PG', 'Pat Graham'],
  ['JH', 'Jake Heckler'],
  ['CK', 'Charlie Knodel'],
  ['CR', 'Cam Resnick'],
  ['JD', 'Justin Diaz'],
  ['JW', 'Joe Walker'],
  ['MM', 'Matt Mahan'],
  ['SM', 'Sām Mozhgani'],
  ['MB', 'Matt Becker'],
  ['JF', 'Jordan Friedman'],
  ['JG', 'Jack Goodwillie'],
  ['CD', 'Carlos Deño'],
  ['JR', 'Jim Roddy'],
];

// Retired / legacy codes — kept for migration tolerance only, not active
var RETIRED_TEAMS = [
  ['JA', 'Former Member JA'],
  ['BD', 'Former Member BD'],
  ['DG', 'Former Member DG'],
  ['KB', 'Former Member KB'],
];

var ALL_TEAMS = ACTIVE_TEAMS.concat(RETIRED_TEAMS);

function buildCodeMap_() {
  var m = {};
  ALL_TEAMS.forEach(function(t) { m[t[0]] = t[1]; });
  return m;
}

// ═══════════════════════════════════════════════════════════════════════
//  ENTRY POINT
// ═══════════════════════════════════════════════════════════════════════
function buildPickLedger() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  Logger.log('buildPickLedger started on: ' + ss.getName());

  writeTeamMapTab_(ss);

  var result = parseFuturePicks_(ss);

  writePickLedgerTab_(ss, result.rows);

  reconcile_(result.rows, result.unparsed);

  Logger.log('buildPickLedger complete — ' + result.rows.length + ' ledger rows written.');
}

// ═══════════════════════════════════════════════════════════════════════
//  WRITE TEAM MAP TAB
// ═══════════════════════════════════════════════════════════════════════
function writeTeamMapTab_(ss) {
  var sheet = getOrClearSheet_(ss, CONFIG.TEAM_MAP_TAB);

  sheet.getRange(1, 1, 1, 2)
       .setValues([['code', 'full_name']])
       .setFontWeight('bold')
       .setBackground('#cfe2ff');

  sheet.getRange(2, 1, ALL_TEAMS.length, 2).setValues(ALL_TEAMS);
  sheet.setFrozenRows(1);
  sheet.autoResizeColumns(1, 2);

  Logger.log('Team Map: ' + ALL_TEAMS.length + ' rows written (' +
             ACTIVE_TEAMS.length + ' active, ' + RETIRED_TEAMS.length + ' retired).');
}

// ═══════════════════════════════════════════════════════════════════════
//  WRITE PICK LEDGER TAB
// ═══════════════════════════════════════════════════════════════════════
function writePickLedgerTab_(ss, rows) {
  var sheet = getOrClearSheet_(ss, CONFIG.LEDGER_TAB);

  var COLS = ['year','round','original_owner','current_owner','condition','status','pick_key'];
  sheet.getRange(1, 1, 1, COLS.length)
       .setValues([COLS])
       .setFontWeight('bold')
       .setBackground('#cfe2ff');

  if (rows.length > 0) {
    var vals = rows.map(function(r) {
      return [r.year, r.round, r.original_owner, r.current_owner,
              r.condition, r.status, r.pick_key];
    });
    sheet.getRange(2, 1, vals.length, COLS.length).setValues(vals);
  }

  sheet.setFrozenRows(1);
  sheet.autoResizeColumns(1, COLS.length);

  Logger.log('Pick Ledger: ' + rows.length + ' rows written.');
}

// ═══════════════════════════════════════════════════════════════════════
//  MAIN PARSER — tries both grid orientations, uses the richer result
// ═══════════════════════════════════════════════════════════════════════
function parseFuturePicks_(ss) {
  var src = ss.getSheetByName(CONFIG.SOURCE_TAB);
  if (!src) throw new Error('Source tab not found: "' + CONFIG.SOURCE_TAB + '"');

  var data    = src.getDataRange().getValues();
  var codeMap = buildCodeMap_();

  var unparsedA = [], unparsedB = [];
  var rowResult  = parseAsRowBlocks_(data, codeMap, unparsedA);
  var colResult  = parseAsColBlocks_(data, codeMap, unparsedB);

  Logger.log('Row-block orientation: ' + rowResult.length + ' picks found, ' +
             unparsedA.length + ' cells unparsed.');
  Logger.log('Col-block orientation: ' + colResult.length + ' picks found, ' +
             unparsedB.length + ' cells unparsed.');

  var rows, unparsed;
  if (rowResult.length >= colResult.length) {
    rows = rowResult; unparsed = unparsedA;
    Logger.log('Using row-block orientation.');
  } else {
    rows = colResult; unparsed = unparsedB;
    Logger.log('Using col-block orientation.');
  }

  // Deduplicate by pick_key (year-round-original_owner); flag collisions
  var seen = {}, deduped = [];
  rows.forEach(function(r) {
    if (!seen[r.pick_key]) {
      seen[r.pick_key] = true;
      deduped.push(r);
    } else {
      Logger.log('WARN duplicate pick_key "' + r.pick_key +
                 '" also found under current_owner=' + r.current_owner + ' — skipped.');
    }
  });

  return { rows: deduped, unparsed: unparsed };
}

// ───────────────────────────────────────────────────────────────────────
//  ORIENTATION A — Team codes are ROW headers (leftmost column)
//                  Year / Round labels are COLUMN headers (top rows)
//
//  Example layout:
//          |          | 2025          | 2026          |
//          |          | R1 | R2 | R3  | R1 | R2 | R3  |
//   BK     |          | PG | BK |     | CR |    |     |
//          | * top-6  |    |    |     |    |    |     |
//   PG     |          | PG | MB |     |    |    |     |
// ───────────────────────────────────────────────────────────────────────
function parseAsRowBlocks_(data, codeMap, unparsed) {
  var nRows = data.length, nCols = data[0].length, rows = [];

  // ── Find year header row: ≥1 cell matching /^20[2-3]\d$/ ────────────
  var yearRow = -1, yearCols = {};
  for (var r = 0; r < Math.min(nRows, 25); r++) {
    var hits = 0, tmp = {};
    for (var c = 0; c < nCols; c++) {
      var v = trim_(data[r][c]);
      if (/^20[2-3]\d$/.test(v)) { hits++; tmp[c] = parseInt(v, 10); }
    }
    if (hits >= 1) { yearRow = r; yearCols = tmp; break; }
  }
  if (yearRow === -1) return rows;

  // ── Find round header row: ≥2 cells matching R?[1-5] ────────────────
  var roundRow = -1, roundCols = {};
  for (var r = yearRow; r <= yearRow + 6 && r < nRows; r++) {
    var hits = 0, tmp = {};
    for (var c = 0; c < nCols; c++) {
      var v = trim_(data[r][c]).toUpperCase();
      var m = v.match(/^R?([1-5])$/);
      if (m) { hits++; tmp[c] = parseInt(m[1], 10); }
    }
    if (hits >= 2) { roundRow = r; roundCols = tmp; break; }
  }
  if (roundRow === -1) return rows;

  // ── Build col → {year, round} map ───────────────────────────────────
  // Support merged-cell sheets: propagate each year rightward to round cols
  var yCols = Object.keys(yearCols).map(Number).sort(function(a,b){return a-b;});
  var rCols = Object.keys(roundCols).map(Number).sort(function(a,b){return a-b;});

  var colMeta = {}; // col → {year, round}
  rCols.forEach(function(rc) {
    var rnd = roundCols[rc];
    if (rnd > 4) return; // exclude R5 / HC
    var yr = null;
    for (var i = yCols.length - 1; i >= 0; i--) {
      if (yCols[i] <= rc) { yr = yearCols[yCols[i]]; break; }
    }
    if (yr) colMeta[rc] = { year: yr, round: rnd };
  });

  if (Object.keys(colMeta).length === 0) return rows;

  // ── Scan body rows ───────────────────────────────────────────────────
  var dataStart    = roundRow + 1;
  var currentTeam  = null;
  var blockPicks   = [];   // ledger rows for current team block
  var conditionMap = {};   // starCount → condition text

  function flushConditions() {
    blockPicks.forEach(function(p) {
      if (p._cm > 0 && conditionMap[p._cm] && !p.condition) {
        p.condition = conditionMap[p._cm];
      }
    });
    blockPicks   = [];
    conditionMap = {};
  }

  for (var r = dataStart; r < nRows; r++) {
    var cell0 = trim_(data[r][0]);
    var code  = extractCode_(cell0, codeMap);

    // New team header
    if (code) {
      flushConditions();
      currentTeam = code;
      continue;
    }

    // Condition row — check cols 0 and 1
    var condText = cell0 || trim_(nCols > 1 ? data[r][1] : '');
    var condM    = condText.match(/^(\*+)\s*(.*)/);
    if (condM) {
      var stars = condM[1].length;
      var text  = condM[2].trim();
      if (!text) {
        for (var c2 = 1; c2 < nCols; c2++) {
          var t = trim_(data[r][c2]);
          if (t && !t.match(/^\*+/)) { text = t; break; }
        }
      }
      conditionMap[stars] = text;
      // Attach immediately to already-collected picks with matching marker
      blockPicks.forEach(function(p) {
        if (p._cm === stars && !p.condition) p.condition = text;
      });
      continue;
    }

    if (!currentTeam) continue;

    // Pick data row — read each configured column
    for (var c in colMeta) {
      c = Number(c);
      var cellVal = trim_(data[r][c]);
      if (!cellVal || cellVal === '-' || cellVal === '—' || cellVal === 'N/A') continue;

      var meta   = colMeta[c];
      var parsed = parseCell_(cellVal, currentTeam, meta.year, meta.round,
                               codeMap, unparsed, r + 1, c + 1);
      if (parsed) {
        blockPicks.push(parsed);
        rows.push(parsed);
      }
    }
  }
  flushConditions();

  return rows;
}

// ───────────────────────────────────────────────────────────────────────
//  ORIENTATION B — Team codes are COLUMN headers (top row)
//                  Year / Round labels are ROW labels (left column)
//
//  Example layout:
//           | BK | PG | JH | ...
//  2025 R1  | PG |    | JH |
//  2025 R2  | BK | MB |    |
//  * = top-6 protected
//  2026 R1  |    | PG |    |
//
//  Also handles separate year / round rows with carry-forward year:
//  2025    |    |    |
//    R1    | PG | BK |
//    R2    | BK | MB |
//  2026    |    |    |
//    R1    |    | PG |
// ───────────────────────────────────────────────────────────────────────
function parseAsColBlocks_(data, codeMap, unparsed) {
  var nRows = data.length, nCols = data[0].length, rows = [];

  // ── Find team header row: ≥3 team codes in non-zero columns ─────────
  var teamRow = -1, teamCols = {};
  for (var r = 0; r < Math.min(nRows, 25); r++) {
    var hits = 0, tmp = {};
    for (var c = 1; c < nCols; c++) {
      var v = trim_(data[r][c]);
      var code = extractCode_(v, codeMap);
      if (code) { hits++; tmp[c] = code; }
    }
    if (hits >= 3) { teamRow = r; teamCols = tmp; break; }
  }
  if (teamRow === -1) return rows;

  // ── Scan body rows for year/round labels and pick data ───────────────
  var dataStart    = teamRow + 1;
  var carryYear    = null;  // carry forward when year and round are in separate rows
  var lastYrRndKey = null;
  var picksByKey   = {};    // key → [picks] for post-hoc condition attachment

  for (var r = dataStart; r < nRows; r++) {
    var label = trim_(data[r][0]);

    // ── Try to parse year+round from the row label ─────────────────
    var yr = null, rnd = null;

    // Combined: "2025R1", "2025 R1", "2025 Round 1", "R1 2025"
    var cm = label.match(/^(20[2-3]\d)\s*[Rr](?:ound\s*)?([1-5])\b/i) ||
             label.match(/^[Rr](?:ound\s*)?([1-5])\s+(20[2-3]\d)/i);
    if (cm) {
      if (label.match(/^20/i)) { yr = parseInt(cm[1], 10); rnd = parseInt(cm[2], 10); }
      else                      { rnd = parseInt(cm[1], 10); yr  = parseInt(cm[2], 10); }
    }

    // Year-only row (no round) → carry forward
    if (!yr && !rnd) {
      var ym = label.match(/^(20[2-3]\d)\s*$/);
      if (ym) { carryYear = parseInt(ym[1], 10); continue; }
    }

    // Round-only row → combine with carried year
    if (!yr && !rnd && carryYear) {
      var rm = label.match(/^[Rr](?:ound\s*)?([1-5])\b/i) || label.match(/^([1-5])\s*$/);
      if (rm) { yr = carryYear; rnd = parseInt(rm[1], 10); }
    }

    if (yr && rnd) {
      if (rnd > 4) { lastYrRndKey = null; continue; } // exclude R5/HC
      lastYrRndKey = yr + '-R' + rnd;
      if (!picksByKey[lastYrRndKey]) picksByKey[lastYrRndKey] = [];

      for (var c in teamCols) {
        c = Number(c);
        var cellVal = trim_(data[r][c]);
        if (!cellVal || cellVal === '-' || cellVal === '—' || cellVal === 'N/A') continue;

        var currentOwner = teamCols[c];
        var parsed = parseCell_(cellVal, currentOwner, yr, rnd,
                                 codeMap, unparsed, r + 1, c + 1);
        if (parsed) {
          picksByKey[lastYrRndKey].push(parsed);
          rows.push(parsed);
        }
      }
      continue;
    }

    // ── Condition row ──────────────────────────────────────────────
    var condM = label.match(/^(\*+)\s*(.*)/);
    if (condM && lastYrRndKey) {
      var stars = condM[1].length;
      var text  = condM[2].trim();
      if (!text) {
        for (var c2 = 1; c2 < nCols; c2++) {
          var t = trim_(data[r][c2]);
          if (t && !t.match(/^\*+/)) { text = t; break; }
        }
      }
      (picksByKey[lastYrRndKey] || []).forEach(function(p) {
        if (p._cm === stars && !p.condition) p.condition = text;
      });
    }
  }

  return rows;
}

// ═══════════════════════════════════════════════════════════════════════
//  PARSE ONE PICK CELL
// ═══════════════════════════════════════════════════════════════════════
/**
 * Interprets one cell under currentOwner's block for the given year+round.
 *
 * Cell formats understood:
 *   "PG"             plain code     → original=PG,  current=currentOwner
 *   "(via MB)"       via clause     → original=MB,  current=currentOwner
 *   "PG (via MB)"    code + via     → original=MB,  current=currentOwner (PG = intermediate)
 *   "via MB)"        malformed      → treated as (via MB)
 *   "(via A via B)"  multi-hop      → original=A (first anchor), current=currentOwner
 *   "PG*"            conditioned    → original=PG, condMarker=1
 *   "PG**"           conditioned    → original=PG, condMarker=2
 *   "COMP"           compensatory   → original=currentOwner, status=compensatory
 *   "FORFEIT"        forfeited      → original=currentOwner, status=forfeited
 *
 * Returns a ledger-row object or null if the cell should be skipped.
 */
function parseCell_(raw, currentOwner, year, round, codeMap, unparsed, sheetRow, sheetCol) {
  if (!raw) return null;

  var cellVal    = raw;
  var status     = 'active';
  var condMarker = 0;  // count of trailing asterisks (0 = none)

  // ── Strip trailing asterisk condition markers ──────────────────────
  var starM = cellVal.match(/(\*+)\s*$/);
  if (starM) {
    condMarker = starM[1].length;
    cellVal    = cellVal.replace(/\*+\s*$/, '').trim();
  }

  // ── Compensatory / forfeited ───────────────────────────────────────
  var upper = cellVal.toUpperCase();
  if (/\bCOMP\b/.test(upper) || /\bCOMPENSATORY\b/.test(upper)) {
    return makeRow_(year, round, currentOwner, currentOwner, '', condMarker, 'compensatory');
  }
  if (/\bFORFEIT/.test(upper)) {
    return makeRow_(year, round, currentOwner, currentOwner, '', condMarker, 'forfeited');
  }

  // ── Normalise malformed via patterns ──────────────────────────────
  // "via XX)" missing opening paren
  if (/\bvia\s+[A-Z]{2,3}\)/i.test(cellVal) && cellVal.indexOf('(') === -1) {
    cellVal = '(' + cellVal;
  }
  // "via XX" with no parens at all (whole cell)
  if (/^\s*via\s+[A-Z]{2,3}\s*$/i.test(cellVal)) {
    cellVal = '(' + cellVal.trim() + ')';
  }

  // ── Determine original_owner ───────────────────────────────────────
  var originalOwner = null;
  var viaM = cellVal.match(/\(via\s+([^)]+)\)/i);

  if (viaM) {
    // Multi-hop: "(via A via B)" — A is the original-owner anchor (first in chain)
    var chain  = viaM[1].trim();
    var codes  = chain.split(/\s+via\s+/i).map(function(s) { return s.trim().toUpperCase(); });
    var anchor = resolveCode_(codes[0], codeMap);
    if (anchor) {
      originalOwner = anchor;
    } else {
      unparsed.push({ row: sheetRow, col: sheetCol, raw: raw,
        reason: 'Unresolved via-chain anchor: "' + codes[0] + '"' });
      return null;
    }
  } else {
    // No via — strip everything except letters; the result is the code
    var cleaned  = cellVal.replace(/[^A-Za-z]/g, '').toUpperCase();
    if (!cleaned) return null;

    var resolved = resolveCode_(cleaned, codeMap);
    if (resolved) {
      originalOwner = resolved;
    } else {
      unparsed.push({ row: sheetRow, col: sheetCol, raw: raw,
        reason: 'Unrecognized code: "' + cleaned + '"' });
      return null;
    }
  }

  return makeRow_(year, round, originalOwner, currentOwner, '', condMarker, status);
}

function makeRow_(year, round, origOwner, curOwner, condition, condMarker, status) {
  return {
    year:           year,
    round:          round,
    original_owner: origOwner,
    current_owner:  curOwner,
    condition:      condition,
    status:         status,
    pick_key:       year + '-' + round + '-' + origOwner,
    _cm:            condMarker,  // internal — not written to sheet
  };
}

// ═══════════════════════════════════════════════════════════════════════
//  CODE EXTRACTION AND RESOLUTION
// ═══════════════════════════════════════════════════════════════════════

/**
 * Extracts a team code from a cell that might be formatted as:
 *   "BK", "BK - Brian Kardane", "Brian Kardane (BK)", "BK's picks"
 * Returns the 2-3 char code string if found in codeMap, else null.
 */
function extractCode_(cellVal, codeMap) {
  if (!cellVal) return null;
  var s = String(cellVal).trim();

  // Direct two-or-three-char uppercase match
  if (codeMap[s.toUpperCase()]) return s.toUpperCase();

  // "XX - Name" or "XX: Name"
  var m = s.match(/^([A-Z]{2,3})\s*[-:]/i);
  if (m && codeMap[m[1].toUpperCase()]) return m[1].toUpperCase();

  // "Name (XX)"
  m = s.match(/\(([A-Z]{2,3})\)\s*$/i);
  if (m && codeMap[m[1].toUpperCase()]) return m[1].toUpperCase();

  // "XX's" or "XX's picks"
  m = s.match(/^([A-Z]{2,3})['']?s?\b/i);
  if (m && codeMap[m[1].toUpperCase()]) return m[1].toUpperCase();

  return null;
}

/**
 * Resolves a raw string to a known team code.
 * Tries exact match first, then first 2–3 characters (catches trailing garbage).
 */
function resolveCode_(raw, codeMap) {
  if (!raw) return null;
  var u = raw.toUpperCase().trim();
  if (codeMap[u]) return u;

  // Trim to 3 chars then 2 chars
  if (u.length > 3 && codeMap[u.substring(0, 3)]) return u.substring(0, 3);
  if (u.length > 2 && codeMap[u.substring(0, 2)]) return u.substring(0, 2);

  return null;
}

// ═══════════════════════════════════════════════════════════════════════
//  SHEET UTILITIES
// ═══════════════════════════════════════════════════════════════════════

function getOrClearSheet_(ss, name) {
  // Refuse to touch the source grid or any unrelated tabs
  var PROTECTED = [CONFIG.SOURCE_TAB, 'Draft Results'];
  if (PROTECTED.indexOf(name) !== -1) {
    throw new Error('Refusing to clear protected tab: "' + name + '"');
  }
  var sheet = ss.getSheetByName(name);
  if (sheet) {
    sheet.clearContents();
    sheet.clearFormats();
  } else {
    sheet = ss.insertSheet(name);
  }
  return sheet;
}

function trim_(v) {
  return (v === null || v === undefined) ? '' : String(v).trim();
}

// ═══════════════════════════════════════════════════════════════════════
//  RECONCILIATION REPORT  (written to execution log, not the sheet)
// ═══════════════════════════════════════════════════════════════════════
function reconcile_(rows, unparsed) {
  var SEP = '═══════════════════════════════════════════════════════════';
  Logger.log('');
  Logger.log(SEP);
  Logger.log('  PICK LEDGER — RECONCILIATION REPORT');
  Logger.log(SEP);

  // ── Row counts by (year, round) ──────────────────────────────────
  var counts = {};
  rows.forEach(function(r) {
    var k = r.year + ' R' + r.round;
    counts[k] = (counts[k] || 0) + 1;
  });
  Logger.log('\nPick counts by (year, round)  ← compare to TRUE/FALSE integrity grid:');
  Object.keys(counts).sort().forEach(function(k) {
    Logger.log('  ' + k + '  →  ' + counts[k] + ' picks');
  });

  // ── Totals ───────────────────────────────────────────────────────
  Logger.log('\nTotal ledger rows: ' + rows.length);

  // ── By status ────────────────────────────────────────────────────
  var statuses = {};
  rows.forEach(function(r) { statuses[r.status] = (statuses[r.status] || 0) + 1; });
  Logger.log('\nBy status:');
  Object.keys(statuses).sort().forEach(function(s) {
    Logger.log('  ' + s + ': ' + statuses[s]);
  });

  // ── Unparsed cells ────────────────────────────────────────────────
  Logger.log('');
  if (unparsed.length === 0) {
    Logger.log('No unparsed cells — all entries resolved cleanly.');
  } else {
    Logger.log('UNPARSED CELLS (' + unparsed.length + ') — fix these in "' +
               CONFIG.SOURCE_TAB + '" and re-run:');
    unparsed.forEach(function(u) {
      Logger.log('  Sheet row ' + u.row + ', col ' + u.col +
                 '  |  raw value: "' + u.raw + '"  |  reason: ' + u.reason);
    });
  }

  Logger.log('\n' + SEP);
}
