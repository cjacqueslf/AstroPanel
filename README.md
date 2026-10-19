# AstroPanel

Widget Windows para astronomia observacional: relógios UTC/local/LST, dados de Sol e Lua, mapa-múndi dia/noite, localização configurável e ícone na bandeja.

## MVP atual

- Interface PySide6 compacta, redimensionável e opcionalmente sempre no topo.
- Relógios atualizados a cada segundo: UTC, horário local com fuso IANA e Tempo Sideral Local aparente.
- Configuração local de observatório (nome, latitude, longitude, altitude e fuso) em `~/.astropanel/settings.json`.
- Seletor visual de coordenadas em mapa-múndi local e edição manual.
- Sol, Lua, crepúsculo astronômico, iluminação lunar e duração da noite astronômica.
- Visualização local do terminador solar e faixas de dia, crepúsculos e noite, sobre contornos mundiais Natural Earth incorporados; sem chamada de API.
- Menu de bandeja para ocultar/mostrar, abrir configurações e sair. Fechar a janela a minimiza para a bandeja.
- Mapa meteorológico padrão **GOES‑19 GeoColor/NOAA via NASA GIBS**, sem chave, georreferenciado e centralizado no observatório, com horário da imagem disponível. MODIS/NASA GIBS permanece disponível como alternativa diária.

## Instalação e execução

### Download para Windows

Baixe o pacote **AstroPanel-0.1.1-Windows-x64.zip** na
[página de versões](https://github.com/cjacqueslf/AstroPanel/releases/latest).
Extraia todo o ZIP e execute `AstroPanel.exe` dentro da pasta AstroPanel.
Não é necessário instalar Python. Mantenha a pasta `_internal` junto do executável.
Configure seu observatório em **Configurações → Localização**.

### Executar pelo código-fonte

Requer Python 3.11 ou posterior.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
astropanel
```

Ou, sem instalação editável:

```powershell
pip install -r requirements.txt
$env:PYTHONPATH = "src"
python -m astropanel.app
```

## Testes

```powershell
pytest
```

## Empacotamento Windows

Instale a dependência opcional de build e gere o pacote portátil:

```powershell
pip install -e ".[build]"
powershell -ExecutionPolicy Bypass -File tools/build_windows.ps1
```

Para distribuição, a etapa posterior recomenda Inno Setup ou WiX para criar o instalador. O recurso “Iniciar com Windows” grava a entrada no Registro do usuário atual depois de ser ativado em Settings.

## Mapas de satélite

O provedor padrão é GOES‑19 GeoColor (`goes19_geocolor`), que não exige chave e consulta os metadados WMS do NASA GIBS para descobrir a imagem disponível. As imagens georreferenciadas são recortadas ao redor do observador, marcado pelas coordenadas dos limites da imagem. O horário UTC aparece no painel; a distribuição pelo GIBS pode chegar com atraso. MODIS/NASA GIBS (`nasa_gibs_free`) permanece como alternativa diária. `src/astropanel/services/map_providers.py` define a interface para integrações posteriores.

## Observação sem Lua

O painel mostra os intervalos com Sol abaixo de −18° e Lua abaixo de 0°, duração total e contagem regressiva. A noite vai do meio-dia local ao meio-dia seguinte; antes do meio-dia, mostra a noite iniciada na data anterior. Cálculo local, sem internet, com busca de cruzamentos a cada cinco minutos e refinamento até um segundo. Não considera nuvens ou obstáculos no horizonte.

## Gerenciador de painéis

O botão **Painéis**, ao lado de Configurações, permite escolher até quatro painéis: Sol e Lua (unificados, preservando os fundos de cada seção), altura da Lua, meteorológico, dia/noite, linha do tempo, visibilidade de planetas, seeing, observação solar e observação lunar. A área de painéis usa uma grade fixa 2 × 2: cada painel ocupa um quadrante, sem rolagem. Os relógios permanecem visíveis e não entram no limite. A seleção é salva e as configurações antigas são migradas automaticamente.

## Observação lunar

Selecione **Painel Observação Lunar** no botão **Painéis**. A imagem representa a fase e a libração da Lua na hora UTC atual, com dados e imagens da NASA SVS/LRO (Dial-A-Moon). O painel mostra iluminação, idade lunar, distância, diâmetro aparente e altitude para o observatório. É uma simulação geocêntrica, com norte para cima; a orientação não acompanha a rotação do disco em relação ao horizonte local.

Clique na imagem para abrir o mapa ampliado na frente do AstroPanel, com zoom, ajuste à janela, escala de 100% e navegação por arraste. O mapa usa a imagem em alta resolução e a camada oficial de nomes da mesma hora: mares iluminados e crateras próximas ao terminador, além dos locais Apollo. A imagem e o mapa são atualizados juntos a cada hora; em caso de falha de conexão, ambos permanecem no último horário disponível. **Atualizar Lua** permite tentar novamente. Os nomes seguem a nomenclatura oficial da NASA. Fonte: https://svs.gsfc.nasa.gov/5587/

A grade usa larguras proporcionais: Sol e Lua têm metade do peso dos painéis maiores. Os gráficos e o mapa dia/noite priorizam a largura disponível; os mapas Meteorológico e Dia e Noite ficam em uma linha própria, dividindo toda a largura e aproveitando a altura disponível. Em janelas estreitas, os dois mapas se empilham. Em janelas estreitas os painéis se empilham para preservar a legibilidade. Janelas com pouca altura permitem rolagem vertical.

A linha do tempo usa o horário real do observatório, do meio-dia ao meio-dia seguinte, e mostra luminosidade solar, Lua acima do horizonte, janelas sem Lua e horários dos eventos. Não tem controle de simulação. As faixas solares e lunares são aproximações visuais por amostragem; os intervalos sem Lua usam os cruzamentos refinados do horizonte.

## Visibilidade de Planetas

O sétimo painel mostra o Sol na primeira linha, Mercúrio, Vênus, Marte, Júpiter, Saturno, Urano e Netuno no centro, e a Lua na última linha, em faixas de meio-dia a meio-dia. O Sol mostra apenas os períodos acima do horizonte; os planetas e a Lua também mostram os períodos favoráveis. A faixa cinza representa altitude acima de 0°; o destaque indica altitude acima de 20° com Sol abaixo de −6°. A coluna à direita mostra a altitude no instante atual e o marcador acompanha o horário real. Passe sobre um planeta para consultar seus intervalos favoráveis.

O cálculo usa posições topocêntricas com efemérides locais do Astropy, sem baixar arquivos ou tabelas. As amostras são interpoladas em intervalos de aproximadamente dez minutos. A visibilidade é geométrica e não considera nuvens, obstáculos ou brilho do céu. Referência: https://docs.astropy.org/en/stable/api/astropy.coordinates.get_body.html

## Mapas meteorológicos online

Em Configurações > Mapas/API, estão disponíveis GOES-19 GeoColor, GOES-19 infravermelho (banda 13, dia e noite), NASA GIBS, Windy (nuvens totais, baixas, médias e altas), InstaRain, Light Pollution Map e Ventusky. As opções do Windy usam o mapa incorporável gratuito, centralizado no observatório, sem chave de API: https://embed.windy.com/config/map. As antigas opções Windy chuva e vento são migradas para nuvens totais ao carregar as configurações.

Light Pollution Map abre centralizado no observatório para consultar estimativas de poluição luminosa; não representa uma medição em tempo real. Ventusky inicia na previsão de cobertura total de nuvens; outras camadas podem ser selecionadas pelos controles do site, conforme sua disponibilidade. InstaRain carrega o mapa público https://www.instarain.com.br/; a região pode ser escolhida pelos controles do próprio site. Os mapas online aparecem dentro do painel Meteorológico, com botão para abrir no navegador e mensagem em caso de falha no carregamento.

A API paga/de desenvolvimento do Windy não é usada. Todos os provedores disponíveis dispensam chave. A exibição dos textos das abas Aparência e Inicialização foi corrigida com cores explícitas para as páginas das configurações, incluindo o modo vermelho.

No Windows, o navegador interno usa WebGL por software (ANGLE/SwiftShader) para exibir as camadas do Windy. A composição gráfica permanece na CPU para evitar falhas de drivers; desativar toda a GPU com `--disable-gpu` impede essas camadas nesta configuração. Reinicie o AstroPanel após atualizar.

O navegador do painel meteorológico preserva os dados dos sites em `~/.astropanel/weather-browser`. O InstaRain recupera o zoom e as opções que o próprio site salva, e é centralizado no observador configurado a cada abertura ou troca de localização. As preferências do navegador externo são independentes.

Todos os mapas ativos indicam a posição das configurações: Windy usa o marcador nativo com `detailLat`/`detailLon`, Ventusky usa um pin geográfico, Light Pollution Map usa o marcador do estado compartilhado e InstaRain recebe um marcador Leaflet. GOES-19 e MODIS usam imagens georreferenciadas WMS do NASA GIBS, recortadas nos limites geográficos ao redor do observador. O marcador acompanha o redimensionamento. As imagens GOES são da NOAA, distribuídas pelo GIBS; o horário UTC da imagem disponível aparece no painel, pois a distribuição pode ter atraso.

**Windy nuvens + InstaRain** combina as nuvens do Windy com as estações públicas carregadas pelo site InstaRain, desenhadas nas coordenadas de cada estação sobre o mesmo mapa. Ao mover ou ampliar o mapa, as duas camadas permanecem alinhadas. O painel oferece visibilidade e opacidade independentes para nuvens e estações. Clique numa estação para ver temperatura, condição, chuva acumulada em 24 h e horário da medição. As nuvens são previsão no horário selecionado no Windy; as estações são observações nos horários informados, com cobertura limitada à rede do InstaRain. Os círculos representam a área indicada para as estações, não uma imagem de radar. Os dados do site são consultados a cada 30 segundos, e falhas são exibidas no painel. Esta integração depende da estrutura dos sites, sem usar uma API paga.

No Light Pollution Map incorporado, o AstroPanel bloqueia as requisições dos serviços de publicidade e oculta os espaços reservados a anúncios, liberando toda a área para o mapa. O filtro é limitado a esse site no navegador interno; os dados das camadas, a atribuição e os controles são preservados.

O painel Meteorológico oferece uma aba para cada opção de mapa, inclusive o combinado Windy + InstaRain. Use as setas da barra quando a janela não comportar todas as abas. Os mapas carregam na primeira visita e permanecem abertos para preservar posição, zoom e controles ao alternar. A aba escolhida é salva como provedor nas configurações e recuperada na próxima abertura. Uma mudança nas coordenadas do observador é aplicada a cada mapa na próxima visita à sua aba; a atualização automática recarrega a aba selecionada.

## Desempenho

O mapa dia/noite usa operações vetorizadas e mantém a iluminação em cache por minuto; a cartografia é reaproveitada enquanto o tamanho não muda. O mapa não é mais redesenhado a cada segundo. Alterações de aparência e seleção de painéis preservam os cálculos astronômicos e o mapa meteorológico carregado, evitando recargas quando o provedor e a localização permanecem iguais. A atualização periódica ainda pode solicitar uma nova imagem ou recarregar a página meteorológica.

### Painel Seeing

Em **Painéis**, selecione **Painel Seeing** (até quatro painéis simultâneos). Usa o local selecionado nas configurações e consulta o produto ASTRO do [7Timer!](https://www.7timer.info/doc.php?lang=en), sem chave de API. Mostra a previsão de seeing em faixas de segundos de arco, evolução por horário, nuvens, precipitação e transparência. Horários no fuso do observatório. Atualiza a cada 30 minutos, com botão para consulta manual, e indica a idade do modelo e falhas de atualização. Os dados são previsões meteorológicas; não representam medição instrumental no observatório.

### Painel Observação Solar

Selecione **Painéis → Painel Observação Solar**. Exibe o contínuo visível SDO/HMI e H-alfa GONG/NSO (656,28 nm), com abertura da imagem original ao clicar. Mostra regiões ativas, contagem reportada de manchas (diferente do índice de Wolf), fluxo F10.7 e classe de raios X/último pico GOES da NOAA. Indica a altura solar no local configurado, horários UTC das fontes, dados antigos e falhas independentes. Atualização a cada 10 minutos ou pelo botão **Atualizar Sol**.


## Cadastro de locais e Sobre

Em **Configurações → Localização**, use **Novo local** para iniciar outro cadastro, mantendo as coordenadas como ponto de partida. Informe um nome único e use **Adicionar local**. Selecione um cadastro existente e use **Atualizar selecionado** para alterar seus dados, inclusive o nome. **Remover local** exclui o cadastro selecionado. Clique em **Salvar** para gravar as mudanças e ativar o local selecionado; **Cancelar** descarta as alterações da janela.

A aba **Sobre** mostra a versão do AstroPanel, autoria, créditos das fontes e o oferecimento do Observatório SONEAR e do canal AstroNEOS. **Ajuda** apresenta os primeiros passos e **Abrir manual do usuário** abre o manual HTML local, distribuído com o aplicativo. O botão **Verificar atualizações** consulta a última versão estável em https://github.com/cjacqueslf/AstroPanel/releases pela API pública do GitHub, sem exigir login. Não instala ou baixa arquivos automaticamente. **Abrir página das versões** mostra as notas e os arquivos disponíveis.


## Publicar uma nova versão

1. Atualize `__version__` em `src/astropanel/__init__.py` e `version` em `pyproject.toml` com o mesmo número (ex.: `0.1.1`).
2. Execute `python -m pytest` e publique o commit no GitHub.
3. Crie uma release pública estável com a tag correspondente (ex.: `v0.1.1`) em https://github.com/cjacqueslf/AstroPanel/releases/new. Inclua notas de alterações e os pacotes de distribuição disponíveis.
4. O botão **Verificar atualizações** detecta a publicação pela API pública do GitHub. Tags sem release, rascunhos e pré-lançamentos não são usados pelo canal estável.


### Canal público de versões

O repositório AstroPanel é público. A consulta de atualizações dispensa autenticação. **Abrir página das versões** mostra as notas e os arquivos disponíveis no GitHub.


### Zoom nas imagens GOES e NASA

Nas abas **GOES GeoColor**, **GOES IR** e **NASA**, use a roda do mouse ou os botões **+ / −** para ampliar de 1× a 8×. Com a imagem ampliada, arraste com o botão esquerdo para navegar. **Ajustar** ou um duplo clique restaura a imagem completa. O marcador e o rótulo do observatório acompanham a imagem. O zoom é preservado na atualização da mesma fonte e local; mudar o local restaura o enquadramento. A ampliação usa a imagem recebida, sem acrescentar resolução ou cobertura geográfica.


### Objetos Deep Sky no painel de Altura da Lua

Clique em **Deep Sky / personalizado…**. Digite um identificador **NGC**, **Messier/M**, **IC** ou **PGC** e use **Buscar catálogo** para obter coordenadas pelo CDS/Sesame (internet necessária). Confira os campos e clique em **Plotar objeto**. A curva verde do objeto é sobreposta à curva branca da Lua, para o observatório e a mesma janela de meio-dia a meio-dia. Os horários seguem o fuso do observatório.

Para um objeto personalizado, preencha nome, ascensão reta (h:m:s ou horas decimais) e declinação (graus sexagesimais com sinal ou graus decimais). Os dois campos são editáveis, inclusive após uma consulta ao catálogo. As coordenadas são equatoriais ICRS/J2000. O cálculo de altitude é local, com amostras de 15 minutos, sem refração, nuvens ou obstáculos. A curva é recalculada ao mudar o local ou a noite. **Remover objeto** retorna à visualização apenas da Lua. O objeto selecionado permanece durante a sessão do aplicativo.


### Sistema Solar no painel de altitude e horários de observação

O botão **Sistema Solar (JPL)…**, ao lado de Deep Sky, consulta **NASA/JPL Horizons** pela designação digitada. Exemplos: `433` (Eros), `2024 YR4`, `C/2023 A3`, `Marte` ou `JPL 499` (ID Horizons). Números simples são números de asteroides; nomes de planetas são reconhecidos em português ou inglês. Cometas usam a solução de aparição selecionada por `CAP` no Horizons. Designações inexistentes e ambíguas são informadas separadamente de falhas de conexão.

A consulta retorna coordenadas astrométricas topocêntricas ICRF/J2000 com o instante correspondente, e uma efeméride de altitude de um minuto para toda a janela de meio-dia a meio-dia. A curva usa a posição variável do objeto, não uma coordenada fixa para toda a noite. Ao mudar o observatório ou a noite, é necessária uma nova consulta online. As coordenadas exibidas no painel acompanham o minuto atual da efeméride em memória.

Tanto objetos **Deep Sky/personalizados** quanto do **Sistema Solar** mostram **nascer**, **ocaso** e **melhor horário na noite astronômica**. O melhor horário maximiza a altitude do objeto acima do horizonte **somente entre o fim do crepúsculo astronômico e o início do próximo** (Sol abaixo de −18°). Se a maior altitude ocorrer fora dessa faixa, o resultado pode ser o começo ou o fim da noite astronômica. Ausência de noite astronômica, objeto abaixo do horizonte durante a noite e objeto circumpolar têm mensagens específicas. Nascer/ocaso referem-se aos eventos dentro da janela desenhada; as datas e o fuso do observatório são indicados para evitar confusão ao cruzar a meia-noite.

Os horários são aproximados: nascer/ocaso são interpolados no cruzamento geométrico de altitude 0° em amostras de um minuto; o melhor horário é obtido na mesma amostragem, incluindo os limites da noite astronômica. Não consideram refração, obstáculos, nuvens ou iluminação lunar.

Referência da API: https://ssd-api.jpl.nasa.gov/doc/horizons.html


### Linhas de referência no Céu agora

A faixa inferior **Linhas** permite mostrar ou ocultar independentemente **Meridiano** (laranja tracejado), **Eclíptica** (amarelo) e **Equador celeste** (ciano traço-ponto). As três linhas começam visíveis; os controles mantêm sua seleção enquanto a janela é usada. O meridiano passa pelo norte, zênite e sul. O equador e a eclíptica são calculados para a data e transformados para o horizonte do observatório, com atualização junto ao céu.
