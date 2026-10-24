# AGENTS.md

## Projekti

OpenLP:n fork, johon tehdään uudet media-, kuva- ja laulupluginit vanhojen pohjalta. Uudet pluginit käyttävät
suoraa tiedostopolkua tietokannan sijaan: valittu kansio levyllä *on* kirjasto.

- Upstream: `https://gitlab.com/openlp/openlp.git` (remote `upstream`; OpenLP ei ole GitHubissa).
- Origin: `takutta/openlp-media` (GitHub, private).
- Työhaara: `feature/filesystem-plugins`. Upstreamin `master` on yhdistetty siihen (`--allow-unrelated-histories`).
- Vanhat pluginit (`media`, `images`, `songs`) jätetään ennalleen; uudet tehdään niiden rinnalle.
- **Ytimeen ei tehdä muutoksia.** Kaikki oma koodi, asetukset, käännökset ja testit ovat hakemistoissa
  `openlp/plugins/` ja `tests/openlp_plugins/`, jotta upstreamin uudet versiot voi yhdistää ilman konflikteja.
  Tarkistus: `git diff upstream/master --stat -- openlp/core resources tests/openlp_core` on tyhjä.

## Tila

| Plugin | Tila |
| --- | --- |
| `media_folder` (Mediakansio) | Valmis ja testattu, ei vielä kokeiltu oikeassa GUI:ssa |
| kuvat | Ei aloitettu |
| `song_folder` (Laulukansio) | Toimii ja testattu, kokeiltu oikeassa GUI:ssa (Xvfb). Ei muokkausnäkymää |

## Mitä on tehty

### Yhteinen koodi: `openlp/plugins/filesystem_library/`

Tämä hakemisto ei ole plugin (siinä ei ole `*plugin.py`-tiedostoa, joten pluginmanager ei lataa sitä), vaan
tiedostojärjestelmäpluginien jaettu kirjasto.

- `libraryitem.py`: pohjaluokka `FileSystemLibraryItem` (alla).
- `translations.py`: `install_translator(polku)` asentaa kansiosta nykyisen kielen `.qm`-käännöksen omalla
  `QTranslator`-oliollaan. Kutsu pluginin konstruktorin alussa ennen `super().__init__()`-kutsua sekä
  `LIBRARY_TRANSLATIONS_PATH`-polulle että pluginin omalle `i18n`-kansiolle.
- `i18n/fi.ts`: pohjaluokan suomennos.

#### `FileSystemLibraryItem`

`FileSystemLibraryItem(MediaManagerItem)` näyttää juurikansion puuna (kansiot ensin, luonnollinen järjestys,
piilotetut ohitetaan). Kuva- ja lauluplugin voivat käyttää samaa luokkaa.

- Juurikansio on asetuksessa `<plugin>/root folder`, ja sen valitsee työkalupalkista "Valitse kansio".
- `QFileSystemWatcher` ja 500 ms:n debounce lataavat puun uudelleen, kun levyllä muuttuu jotain.
  Avatut kansiot ja valinta säilyvät.
- Tiedostojen lisäys (dialogi tai drag & drop) kopioi tiedostot valittuun kansioon. Mitään ei ylikirjoiteta.
- Raahaus kirjaston sisällä siirtää tiedostoja levyllä. "Lisää kansio" luo oikean hakemiston.
- Poisto kysyy vahvistuksen ja siirtää tiedostot roskakoriin (`QFile.moveToTrash`).
- Puun itemeissä `UserRole` = `Path`, `ItemTypeRole` (`UserRole + 1`) = `'folder'` / `'file'`.
- Aliluokka toteuttaa `is_supported_file()` ja `generate_slide_data()`. Lisäksi se voi ylikirjoittaa
  `load_item()`- ja `delete_item()`-metodit.
- `on_add_click()` lisää jokaisen valitun tiedoston palveluun erikseen (valittu kansio = sen suorat tiedostot).
  `_get_tree_item(item)` muuntaa `generate_slide_data()`:lle annetun arvon (None / `QModelIndex` / item) puun
  itemiksi.
- Luokka rekisteröi itse oletusasetukset (`root folder`, `last directory` ja listanäkymän pikanäppäimet
  `shortcuts/listView<Name>…`). Muuten `create_widget_action` kaatuu KeyErroriin.

### Media Folder -plugin: `openlp/plugins/media_folder/`

- Plugin rekisteröi oman `media_folder/status`-oletusasetuksensa (`Settings.extend_default_settings`).
- Ydin tuntee vain omien pluginiensa palvelukohteiden kuvakkeet, joten `generate_slide_data()` asettaa kuvakkeen
  itse. Lisäksi palvelukohteella on `OnLoadUpdate`, jolloin `service_load()` palauttaa kuvakkeen, kun lista avataan
  tiedostosta.
- Remote-API:n media play/pause/stop (`/api/v2/media/*`) ei toimi media_folder-kohteille, koska ydin tarkistaa
  pluginin nimen (`name != 'media'`). Tähän ei ole tehty kiertotietä. Slidejen vaihto ja muu remote-ohjaus toimivat.
  Upstreamille voisi ehdottaa tarkistuksen vaihtamista muotoon `service_item.is_media()`.
- Pluginin nimi on `media_folder`. Nimen täytyy vastata `de_hump(MediaFolderPlugin)`-muotoa, koska `State`
  hakee pluginia nimellä `<nimi>_plugin`.
- Listaa ääni- ja videotiedostot `get_supported_media_suffix()`-funktion perusteella, kirjainkoosta
  riippumatta.
- Kansion lisääminen palveluun lisää jokaisen sen mediatiedoston erikseen.
- Verkko- ja laitestriimit jätettiin pois, koska niillä ei ole tiedostopolkua.

### Song Folder -plugin: `openlp/plugins/song_folder/`

Laulut ovat OpenLyrics-tiedostoja (`*.xml`, kirjainkoosta riippumatta) kansiossa. Totuus on aina tiedostoissa,
tietokantaa ei ole.

- `lib/songfile.py`: tietokannaton jäsennin. `parse_song_file()` / `parse_song_xml()` palauttaa `FileSong`-olion
  (nimet, tekijät tyyppeineen, copyright, CCLI, kommentit, laulukirjat, aiheet, säejärjestys, säkeet).
  Virheellinen tiedosto nostaa `SongFileError`in.
  - Rivien käsittely (sointumerkit, muotoilutagit, `<br/>`) käyttää songs-pluginin `OpenLyrics`-luokan
    apumetodeja (`_process_lines_mixed_content`, `_process_formatting_tags`), joten tulos on sama kuin
    songs-pluginissa. `OpenLyrics(None)` luodaan laiskasti, koska sen konstruktori lukee asetuksia.
  - Kaksi poikkeamaa songs-pluginista: XML:n sisennykset ja rivinvaihdot poistetaan (OpenLyricsissä rivinvaihto on
    vain `<br/>`), ja sivunvaihdon `<p style="page-break-after…"/>` jälkeinen teksti säilyy (songs-plugin
    hukkaa sen).
  - Tuntemattomat muotoilutagit lisätään väliaikaisina (`temporary=True`), asetuksia ei muuteta.
  - Jäsennin ei lataa ulkoisia entiteettejä eikä verkkoa (`resolve_entities=False`, `no_network=True`).
  - `ordered_verses()`: säejärjestyksen merkintä osuu koko nimeen (`v1a`), tagiin ja numeroon (`v1`, kaikki osat)
    tai pelkkään tagiin (`c`). Ilman säejärjestystä säkeet näytetään tiedoston järjestyksessä.
- `lib/songindex.py`: `SongIndex` on hakuindeksi muistissa. Tiedosto jäsennetään uudelleen vain, kun sen
  `st_mtime_ns` tai koko muuttuu. `update(polut)` synkronoi indeksin puun tiedostoihin (kutsutaan jokaisen
  `reload()`in jälkeen). `search(teksti)` vaatii kaikki sanat mistä tahansa kentästä tai tiedostonimestä
  (normalisoitu: pienet kirjaimet, ei välimerkkejä, sointuja eikä muotoilutageja). Indeksiä ei tallenneta
  levylle. Jos käynnistys on isolla kirjastolla hidas, sen voi myöhemmin välimuistittaa pluginin datakansioon.
- `lib/mediaitem.py`: `SongFolderMediaItem(FileSystemLibraryItem)`.
  - Puussa näkyy laulun nimi, ja tooltipissä on vaihtoehtoinen nimi, tekijät ja polku. Tiedosto, jota ei voi lukea,
    näkyy tiedostonimellä ja virhekuvakkeella, ja virhe on tooltipissä.
  - Hakukenttä listan yläpuolella suodattaa puuta kirjoitettaessa. Kansiot, joissa ei ole osumia, piilotetaan, ja
    osumia sisältävät kansiot avataan. Suodatus säilyy, kun puu ladataan uudelleen.
  - `generate_slide_data()`: säkeet säejärjestyksessä, pakotettu sivunvaihto (`[--}{--]`) jakaa slidet ja
    valinnainen jako (`[---]`) toimii `CanSoftBreak`-ominaisuudella. Alatunniste tehdään songs-pluginin
    `songs/footer template` -mallilla (sama ulkoasu kuin songs-pluginissa). `audit` asetetaan, joten
    songusage-plugin kirjaa käytön. `data_string['file path']` kertoo lähdetiedoston.
  - Remote-API:n haku (`search()`) käyttää indeksiä ja palauttaa tiedostopolun id:nä.
- Plugin rekisteröi `song_folder/status`-oletusasetuksen ja songs-pluginin `song_footer`-oletuksen, joten
  alatunniste toimii, vaikka songs-plugin olisi pois päältä.
- Puuttuu vielä:
  - Muokkausnäkymä. `editsongform.py` on tietokantasidonnainen, joten tarvitaan oma lomake, joka kirjoittaa
    OpenLyrics-tiedoston (ehkä songs-pluginin `OpenLyrics.song_to_xml`-logiikalla ilman tietokantaa).
  - Uusi laulu, taustamusiikki (`HasBackgroundAudio`), ensimmäisen sliden tila ja isot kirjaimet.
  - Remote-API:n transponointi (`/api/v2/plugins/songs/transpose-live-item`) ei toimi, koska ydin tarkistaa
    nimen (`name != 'songs'`). Sama tilanne kuin media_folderin play/pause-kutsuissa.

### Suomennokset: `openlp/plugins/*/i18n/fi.ts`

- Käännökset ovat pluginien omissa tiedostoissa, eivät `resources/i18n/fi.ts`:ssä, jota upstream päivittää.
- `filesystem_library/i18n/fi.ts`: konteksti `OpenLP.FileSystemLibraryItem` sekä pohjaluokan käyttämät ytimen
  tekstit (`OpenLP.Ui` "Add folder" jne.), joista osa puuttuu ytimen suomennoksesta.
- `media_folder/i18n/fi.ts`: kontekstit `MediaFolderPlugin`, `MediaFolderPlugin.MediaItem` ja käytetyt
  `MediaPlugin.MediaItem`-tekstit.
- `song_folder/i18n/fi.ts`: kontekstit `SongFolderPlugin`, `SongFolderPlugin.MediaItem` sekä alatunnisteen
  `OpenLP.Ui`- ja `SongsPlugin.MediaItem`-tekstit. Tekijätyyppien nimet (`SongsPlugin.AuthorType`) tulevat ytimen
  suomennoksesta.
- Termistö noudattaa olemassa olevaa suomennosta: service = "Lista", live = "Esitys".
- Päivitys lähdekoodin muututtua (esimerkki): `uv run pyside6-lupdate openlp/plugins/media_folder/*.py
  openlp/plugins/media_folder/lib/*.py -ts openlp/plugins/media_folder/i18n/fi.ts`. lupdate ei löydä ytimen
  `UiStrings`-tekstejä, joten `OpenLP.Ui`-konteksti on lisätty käsin.
- `.qm`-tiedostoja ei commitoida. Lähdekoodista ajettaessa käännä kaikki:
  ```
  uv run pyside6-lrelease resources/i18n/fi.ts -qm resources/i18n/fi.qm
  for d in openlp/plugins/*/i18n; do uv run pyside6-lrelease $d/fi.ts -qm $d/fi.qm; done
  ```

## Kehitys

```
uv sync --all-extras
QT_QPA_PLATFORM=offscreen uv run pytest tests -q
uv run flake8 <tiedostot>      # rivin maksimipituus 120
uv run python run_openlp.py
```

- Testit: `tests/openlp_plugins/filesystem_library/`, `tests/openlp_plugins/media_folder/` ja
  `tests/openlp_plugins/song_folder/`.
- Laulun lukeminen voi lisätä globaaliin `FormattingTags.html_expands`-listaan väliaikaisia tageja, mikä rikkoo
  songs-pluginin testin `test_process_formatting_tags`. `song_folder/conftest.py` palauttaa listan jokaisen
  testin jälkeen.
- Ympäristö pilvikontissa: `uv sync --all-extras` tarvitsee `libicu-dev`- ja `libpq-dev`-paketit, ja Qt tarvitsee
  esim. `libegl1`, `libgl1`, `libxkbcommon0` ja `libxcb-cursor0` (Xvfb-ajoon).
- GUI:n kokeilu ilman näyttöä: `xvfb-run -a uv run python run_openlp.py -p -P <kansio>`, ja rootina lisäksi
  `QTWEBENGINE_DISABLE_SANDBOX=1`. Ensikäynnistyksen ohjattu toiminto ja versiovarmuuskopion kysely pitää ohittaa
  asetuksilla tai skriptissä.
- Testeissä oikeita widgettejä luotaessa `ActionList.shortcut_map` pitää tyhjentää testien välillä.
- Upstreamin `tests/openlp_core/lib/test_mediamanageritem.py` jättää `MediaManagerItem._setup`-patchin voimaan
  (`setup_patcher.stop` ilman sulkuja). Pluginien testipakettien `conftest.py` kutsuu siksi `patch.stopall()`.
  Uusiin testipaketteihin, jotka luovat oikeita media manager -itemejä, tarvitaan sama fixture.
- `uv run` / `uv sync` muuttaa `uv.lock`-tiedostoa (lisää `packaging`). Palauta se, ellei muutosta tarkoiteta.
- Käytä tiedostoissa samaa GPL-lisenssiotsikkoa kuin muualla koodissa.

## Seuraavaksi

Uudet pluginit tehdään samalla mallilla kuin `media_folder` ja `song_folder`: oletusasetukset, käännökset,
kuvakkeet ja testit pluginin omassa hakemistossa, ei ytimessä. Vanhojen pluginien koodia saa käyttää uudelleen
importtaamalla, mutta niitä ei muokata.

1. Kuvaplugin `FileSystemLibraryItem`-luokan päälle (pikkukuvat, taustan korvaus ja teema-asetukset
   `images`-pluginista).
2. Laulukansion muokkausnäkymä ja "Uusi laulu", jotka kirjoittavat OpenLyrics-tiedoston (ks. "Puuttuu vielä"
   yllä). Kirjoituksen pitää säilyttää tiedostossa ne kentät, joita lomake ei tunne.
