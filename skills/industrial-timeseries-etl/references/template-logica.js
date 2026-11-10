// TEMPLATE genérico de lógica de curadoria para sandbox (módulo ES síncrono: ctx -> { facts }).
// Forma de ctx assumida: window {start, end} ISO UTC, items[] ({ entity, kind, ts, values, metadata.quality }), prior[], params.
// Confira com o contrato da plataforma, ajuste o bloco "AJUSTE AQUI" e rode os 12 casos da seção 11 da skill antes de ativar.
//
// O que ele faz, por janela (hora UTC) e por entity (série/tag):
//   - total_<x>:        soma dos deltas positivos do totalizador (reset conta, não soma; amostra anterior colada entra)
//   - minutos_rodando / minutos_parado / paradas / disponibilidade_pct: duração por estado (0/1), recortada na janela
//   - <vazao>_media_rodando: média da vazão só com o estado = 1
// Regras que valem para qualquer lógica (ver SKILL.md, seção 11):
//   - função SÍNCRONA, sem async/await/Promise, sem import, sem timers, sem fetch, sem process/require.
//   - ctx chega congelado (deep freeze): nunca ordene ctx.items no lugar; copie antes.
//   - todo fato tem periodStart/periodEnd DENTRO de [ctx.window.start, ctx.window.end]; fora disso a janela inteira falha.
//   - não emita fato quando não há dado válido (ausência não é zero).

// ── AJUSTE AQUI ──────────────────────────────────────────────────────────────
// Chaves de `values` cadastradas na origem para este tipo de equipamento.
const CHAVES = { vazao: 'flow', estado: 'status', totalizador: 'accumulated' };
// Nomes das métricas (snake_case, regex ^[a-z][a-z0-9_.]*$) e unidades.
const METRICAS = { total: 'toneladas', vazao: 'vazao_media_rodando' };
const UNIDADES = { total: 't', vazao: 't/h' };
// Códigos de metadata.quality[chave] que AINDA valem como leitura (o equipamento respondeu, só o número não mudou).
// Código da plataforma para valor congelado; aceitável em totalizador e estado; para vazão, geralmente não.
const QUALIDADE_ACEITA = 'uncertain:stuck';
// ── fim do bloco de ajuste ───────────────────────────────────────────────────

function num(v) {
  return typeof v === 'number' && isFinite(v) ? v : null;
}

function arred(v, casas) {
  const f = Math.pow(10, casas);
  return Math.round(v * f) / f;
}

// Valor de values[chave] se a qualidade permite; senão null. Sem metadata.quality[chave] = leitura boa.
function leitura(item, chave, aceitaCongelado) {
  const v = num(item.values ? item.values[chave] : undefined);
  if (v === null) return null; // leitura que falhou não aparece em values
  const q = item.metadata && item.metadata.quality ? item.metadata.quality[chave] : undefined;
  if (q === undefined || q === null || q === 'good') return v;
  if (aceitaCongelado && q === QUALIDADE_ACEITA) return v;
  return null; // uncertain:sentinel|range|status|nan, ou qualquer outra marca
}

// Série em ordem de tempo, sem timestamps repetidos (a última leitura do mesmo instante vence).
// Copia: ctx.items é imutável.
function serie(itens) {
  const lista = [];
  for (let i = 0; i < itens.length; i++) {
    const t = Date.parse(itens[i].ts);
    if (isFinite(t)) lista.push({ t: t, item: itens[i] });
  }
  lista.sort(function (a, b) {
    return a.t - b.t;
  });
  const out = [];
  for (let i = 0; i < lista.length; i++) {
    if (out.length && out[out.length - 1].t === lista[i].t) out[out.length - 1] = lista[i];
    else out.push(lista[i]);
  }
  return out;
}

function calcular(entity, itens, anterior, ini, fim, p) {
  const intervaloMs = p.intervaloSegundos * 1000;
  const tetoMs = intervaloMs * p.fatorBuraco; // quanto tempo no máximo uma amostra "vale"
  const tolMs = 5000; // folga de relógio ao decidir se a amostra anterior ainda é contínua
  const amostras = serie(itens);
  const info = { amostras: amostras.length, descartadas: 0, resets: 0, buracos: 0 };
  if (!amostras.length) return { fatos: [], info: info };

  // 1) Amostra anterior à janela: ponto de partida, só se estiver colada (sem buraco).
  let ant = null;
  if (p.usarAmostraAnterior && anterior) {
    const ta = Date.parse(anterior.ts);
    if (isFinite(ta) && ta < ini && amostras[0].t - ta <= tetoMs + tolMs) ant = { t: ta, item: anterior };
  }
  const base = ant ? [ant].concat(amostras) : amostras;

  // 2) Totalizador: soma só os deltas positivos entre leituras válidas consecutivas.
  let total = null;
  let anteriorTot = null;
  for (let i = 0; i < base.length; i++) {
    const v = leitura(base[i].item, CHAVES.totalizador, true);
    if (v === null) {
      if (base[i].t >= ini) info.descartadas++;
      continue;
    }
    if (anteriorTot !== null) {
      if (total === null) total = 0;
      if (v > anteriorTot) total += v - anteriorTot;
      else if (v < anteriorTot) info.resets++; // reset/rollover: novo ponto de partida, não soma
    }
    anteriorTot = v;
  }

  // 3) Estado (0/1): cada amostra vale até a próxima (no máximo tetoMs); a última vale um intervalo.
  //    O trecho é recortado na janela: horas vizinhas não contam o mesmo tempo duas vezes.
  const validas = [];
  for (let i = 0; i < base.length; i++) {
    const v = leitura(base[i].item, CHAVES.estado, true);
    if (v === 1 || v === 0) validas.push({ t: base[i].t, rodando: v === 1 });
  }
  let msRodando = 0;
  let msParado = 0;
  let paradas = 0;
  let temEstado = false;
  for (let i = 0; i < validas.length; i++) {
    const a = validas[i];
    const prox = i + 1 < validas.length ? validas[i + 1] : null;
    if (a.t >= ini) temEstado = true;
    if (prox && a.rodando && !prox.rodando && prox.t >= ini) paradas++;
    let dur = prox ? prox.t - a.t : intervaloMs;
    if (prox && dur > intervaloMs + tolMs && prox.t >= ini) info.buracos++;
    if (dur > tetoMs) dur = tetoMs; // buraco de dados não vira "rodando" nem "parado" além do teto
    const de = Math.max(a.t, ini);
    const ate = Math.min(a.t + dur, fim);
    if (ate > de) {
      if (a.rodando) msRodando += ate - de;
      else msParado += ate - de;
    }
  }

  // 4) Média da vazão só com o estado = 1 na mesma amostra.
  let somaVazao = 0;
  let nVazao = 0;
  for (let i = 0; i < amostras.length; i++) {
    const it = amostras[i].item;
    if (leitura(it, CHAVES.estado, true) !== 1) continue;
    const f = leitura(it, CHAVES.vazao, false);
    if (f === null || f < 0) continue;
    somaVazao += f;
    nVazao++;
  }

  // 5) Fatos. Sempre o período da janela inteira; sempre attributes.unit.
  const fatos = [];
  const add = function (metric, value, unit, extra) {
    const attributes = { unit: unit };
    if (extra) for (const k of Object.keys(extra)) attributes[k] = extra[k];
    fatos.push({ entity: entity, metric: metric, periodStart: p.inicioIso, periodEnd: p.fimIso, value: value, attributes: attributes });
  };
  if (total !== null) add(METRICAS.total, arred(total, 3), UNIDADES.total, { resets: info.resets, usouAmostraAnterior: !!ant });
  if (temEstado) {
    const minR = msRodando / 60000;
    const minP = msParado / 60000;
    // numerador e denominador junto do percentual: permite reagregar (dia, mês) somando minutos, nunca média de %.
    add('minutos_rodando', arred(minR, 3), 'min', { buracos: info.buracos });
    add('minutos_parado', arred(minP, 3), 'min');
    add('paradas', paradas, 'un');
    if (minR + minP > 0) add('disponibilidade_pct', arred((minR / (minR + minP)) * 100, 2), '%');
  }
  if (nVazao > 0) add(METRICAS.vazao, arred(somaVazao / nVazao, 3), UNIDADES.vazao, { amostras: nVazao });
  return { fatos: fatos, info: info };
}

export default function (ctx) {
  // Params opcionais da versão (objeto JSON; ausente = {}), com padrões defensivos.
  const prm = ctx.params || {};
  const intervalo = num(prm.intervaloSegundos);
  const fator = num(prm.fatorBuraco);
  const p = {
    intervaloSegundos: intervalo !== null && intervalo > 0 ? intervalo : 60, // intervalo REAL de amostragem (confirme no cadastro)
    fatorBuraco: fator !== null && fator >= 1 ? fator : 2,
    usarAmostraAnterior: prm.usarAmostraAnterior !== false,
    inicioIso: ctx.window.start,
    fimIso: ctx.window.end,
  };
  const ini = Date.parse(ctx.window.start);
  const fim = Date.parse(ctx.window.end);

  // Agrupa por entity. Filtra kind: evento (ex.: RFID) tem outro formato e outra lógica.
  const porEntidade = {};
  const ordem = [];
  for (let i = 0; i < ctx.items.length; i++) {
    const it = ctx.items[i];
    if (it.kind !== 'sample' || !it.values) continue;
    if (!Object.prototype.hasOwnProperty.call(porEntidade, it.entity)) {
      porEntidade[it.entity] = { itens: [], anterior: null };
      ordem.push(it.entity);
    }
    porEntidade[it.entity].itens.push(it);
  }
  // ctx.prior: último item de cada série antes da janela. Só das entidades que têm amostra na janela.
  for (let i = 0; i < ctx.prior.length; i++) {
    const it = ctx.prior[i];
    if (it.kind !== 'sample' || !Object.prototype.hasOwnProperty.call(porEntidade, it.entity)) continue;
    const atual = porEntidade[it.entity].anterior;
    if (!atual || Date.parse(it.ts) > Date.parse(atual.ts)) porEntidade[it.entity].anterior = it;
  }

  const fatos = [];
  let amostras = 0;
  let descartadas = 0;
  let resets = 0;
  let buracos = 0;
  for (let i = 0; i < ordem.length; i++) {
    const e = ordem[i];
    const r = calcular(e, porEntidade[e].itens, porEntidade[e].anterior, ini, fim, p);
    for (let j = 0; j < r.fatos.length; j++) fatos.push(r.fatos[j]);
    amostras += r.info.amostras;
    descartadas += r.info.descartadas;
    resets += r.info.resets;
    buracos += r.info.buracos;
  }
  // UMA linha de log por janela (o sandbox costuma limitar linhas e tamanho; confira o contrato).
  console.log('entidades=' + ordem.length + ' amostras=' + amostras + ' descartadas_totalizador=' + descartadas + ' resets=' + resets + ' buracos=' + buracos + ' fatos=' + fatos.length);
  return { facts: fatos };
}
