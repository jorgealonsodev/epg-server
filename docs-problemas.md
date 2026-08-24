# Canales con problemas

Tras aplicar los alias verificados: **228 de 471** canales con guía.

Los 243 restantes se reparten en cuatro grupos, y **solo uno es accionable**.

## 1. Emparejados pero a revisar (21)

Coincidencia difusa. Revisados uno por uno; **uno está mal**:

| Lista | EPG asignado | Veredicto |
|---|---|---|
| `AndaluciaTV` | ES - Andalucía TV | correcto |
| `CASTILLA LA MANCHA` | ES - Castilla la Mancha TV | correcto |
| `COMEDYCENTRAL` | ES - Comedy Central | correcto |
| `COMEDYCENTRAL FULL HD` | ES - Comedy Central | correcto |
| `DAZN MOTO GP FULL HD` | ES - DAZN MotoGP | correcto |
| `DAZN MOTO GP HD` | ES - DAZN MotoGP | correcto |
| `DAZN MOTO GP SD` | ES - DAZN MotoGP | correcto |
| `DAZNBaloncesto` | ES - DAZN Baloncesto | correcto |
| `DAZNBaloncesto2` | ES - DAZN Baloncesto 2 | correcto |
| `DAZNBaloncesto3` | ES - DAZN Baloncesto 3 | correcto |
| `EUROSPORT2HD` | ES - Eurosport 2 | correcto |
| `LA SEXTA 4K` | ES - La Sexta | correcto |
| `LA SEXTA FULL HD` | ES - La Sexta | correcto |
| `LA SEXTA HD` | ES - La Sexta | correcto |
| `M+ DEPORTES2 FULL HD` | ES - M+ Deportes 2 | correcto |
| `Movistar+1 4K` | ES - Movistar F1 | **INCORRECTO** — es el canal +1 (timeshift), no Fórmula 1 |
| `Realmadrid TV FULL HD` | ES - Real Madrid TV | correcto |
| `Realmadrid TV HD` | ES - Real Madrid TV | correcto |
| `SkyShowtime 1` | ES - SkyShowtime1 | correcto |
| `WARNERTV` | ES - Warner TV | correcto |
| `WARNERTV FULL HD` | ES - Warner TV | correcto |

Para corregirlo, excluí `Movistar+1` en `ALIASES` o subí `FUZZY_CUTOFF`.

## 2. Canales '24/7' de un solo título (~73)

Emiten un título en bucle continuo. **No existe EPG para ellos en ninguna fuente**:
no tienen parrilla, por definición. No son un fallo del emparejamiento.

Ejemplos: `24/7 Bones`, `24/7 Chernobyl`, `24/7 Peppa Pig 1`.

## 3. Familias numeradas de eventos (81 entradas, 11 familias)

Canales rotativos que se asignan a un evento puntual. Sin parrilla fija.

| Familia | Entradas |
|---|---:|
| super movie | 12 |
| dazn acb | 10 |
| netflix | 10 |
| laliga tv hypermotion | 9 |
| movistar infantiles | 9 |
| cinelatino | 7 |
| new alquiler | 6 |
| tv nacional | 6 |
| movistar+ marvel | 5 |
| m+ cinesur | 4 |
| procaja tv | 3 |

## 4. Canales reales ausentes de esta fuente — **AQUÍ SÍ SE PUEDE ACTUAR**

Verificado uno por uno contra el EPG. Estos son canales de emisión normal,
con parrilla, que sencillamente no están en `iptv-epg.org`:

| Canal | Estado en el EPG |
|---|---|
| DMAX | ausente |
| FDF | ausente |
| UFC | ausente |
| DAZN RALLY TV | ausente |
| 101TV | ausente |
| PRIMERA FEDERACION | ausente |
| LALIGA INSIDE | ausente |
| UEFA Champions League | ausente |
| Apple TV+ 1 / 2 | ausente |
| Prime Video 1 / 2 | ausente |
| Rakuten TV (3) | ausente |
| LALIGA TV HYPERMOTION (9) | ausente |
| MULTIDEPORTE | ausente |
| ONETORO / MUNDOTORO | ausente |
| CANAL DECASA | ausente |
| SkyShowtime 2 | solo existe SkyShowtime1 |
| CANAL SUR 2 | solo existe Canal Sur y Canal Sur Andalucía |
| M+ ACCION 2 / DRAMA 2 / VAMOS 3 | solo existe la versión sin número |
| Locales (7TV/PTV/CANAL Málaga, Torrevisión) | ausente |

**Única vía de mejora**: añadir otra fuente a `EPG_SOURCES` (acepta varias
separadas por coma y las fusiona, la primera gana ante ids repetidos).

## Dudoso, decidí vos

- `GOL PLAY` → el EPG tiene `ES - GOL`. Probablemente el mismo canal renombrado,
  pero no lo confirmé. Si lo es, añadí `"gol play": "gol"` a `ALIASES`.
