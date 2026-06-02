# osu-Py

OSU-Py é um projeto fan-made de jogo de ritmo inspirado no OSU!, feito em Python com pygame-ce. O objetivo e carregar beatmaps no formato `.osu`, tocar a musica correspondente e renderizar uma gameplay jogavel com hit circles, sliders, approach circles, combo, score, accuracy, cursor customizado e selecao de musicas/dificuldades.

O projeto ainda esta em desenvolvimento, mas a gameplay principal ja esta funcional e vem sendo reorganizada aos poucos para facilitar a manutencao, melhorar a performance e separar melhor as responsabilidades entre loader, cenas, renderizadores e regras de jogo.

## Funcionalidades atuais

- Leitura de pastas de beatmaps dentro de `songs/`.
- Parse de metadata, difficulty, timing points, hit circles, sliders e cores de combo.
- Gameplay com circles, sliders, reverse markers, slider ball, fade in/out, miss pop, score, combo e accuracy.
- Renderizacao de cursor, notas, sliders, spinner, HUD e menu usando a skin em `assets/skins/default/`.
- Menus com `pygame_gui` para selecionar musica e dificuldade.
- Suporte a fullscreen e troca de fullscreen para modo janela e vice-versa com `F11`.

## Requisitos

- Python 3.12 recomendado.
- Windows foi o ambiente principal de desenvolvimento/teste.
- Dependencias listadas em `requirements.txt`.

Instale as dependencias com:

```bash
pip install -r requirements.txt
```

Em alguns ambientes Windows, o comando pode ser:

```bash
py -3.12 -m pip install -r requirements.txt
```

## Como rodar

```bash
py -3.12 main.py
```

Ou, se `python` apontar para a versao correta:

```bash
python main.py
```

## Beatmaps

Coloque as musicas dentro da pasta `songs/`. Cada beatmap deve manter sua estrutura original, incluindo pelo menos:

- Arquivo `.osu`.
- Arquivo de audio referenciado pelo `.osu`.
- Arquivo da música principal `.wav/.mp3`.
- Assets opcionais do beatmap, quando existirem.

O loader percorre as subpastas de `songs/`, encontra arquivos `.osu` e monta a lista de dificuldades disponiveis.
Baixe as músicas do seu interese diretamente no site oficial do game, https://osu.ppy.sh/beatmapsets. 

## Controles

- `Z` ou `X`: acertar objetos.
- `Clique esquerdo` ou `clioque direito` do mouse para acertar os objetos.
- `Esc`: sair da gameplay ou voltar uma cena.
- `F3`: alternar profiler de performance.
- `F11`: alternar fullscreen.
- `Alt + F4`: sair do jogo.

## Performance e profiler

Durante testes em PCs fracos, pressione `F3` para abrir o profiler interno. Ele mostra FPS, tempo medio do frame, p95, piores frames e custo de eventos/update/render/flip/pacer. O mesmo resumo tambem aparece no terminal a cada poucos segundos.

Tambem e possivel iniciar o jogo ja com o profiler ativo:

```bash
$env:PYOSU_PROFILE="1"; py -3.12 main.py
```

O jogo usa `240 FPS` como alvo padrao para reduzir stutter em PCs fracos. Para testar outro limite:

```bash
$env:PYOSU_TARGET_FPS="360"; py -3.12 main.py
```

Para testar o modo de menor latencia com maior uso de CPU:

```bash
$env:PYOSU_BUSY_FRAME_PACER="1"; py -3.12 main.py
```

## Skins

Os assets padrao ficam concentrados em `assets/skins/default/`. Para testar outra skin mantendo os mesmos nomes de arquivo:

```bash
$env:PYOSU_SKIN_DIR="assets/skins/minha-skin"; py -3.12 main.py
```

## Estrutura do projeto

- `main.py`: ponto de entrada.
- `core/`: loop principal, audio, loader de beatmaps, scene manager e calculos de gameplay.
- `scenes/`: menus, selecao de musica/dificuldade e cena de gameplay.
- `rendering/`: renderizacao de primitivas, cursor e sliders.
- `assets/skins/default/`: skin padrao com imagens e sons usados pelo jogo.
- `songs/`: beatmaps usados nos testes.
- `ui/`: espaco reservado para componentes/temas de interface.

## Observacoes de desenvolvimento

O projeto prioriza manter uma base simples e facil de evoluir. A cena de gameplay ainda concentra bastante logica, entao uma das proximas etapas será fragmentar melhor toda a estrutura de código em componentes menores, especialmente HUD, lifecycle dos objetos, julgamento de hit e renderizacao especifica de notas.

Se aparecer o aviso `libpng warning: iCCP: known incorrect sRGB profile`, ele normalmente indica um perfil de cor invalido em algum PNG carregado pelo pygame. Em geral isso nao impede o jogo de funcionar.

## Aviso

- Esse projeto é feito totalmente por um fã, sem qualquer intuito comercial e não possui qualquer ligação com o jogo oficial e seus responsáveis. 
