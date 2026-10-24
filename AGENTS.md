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
| `media_folder` (Mediakansio) | Valmis ja testattu, käynnistyy oikeassa sovelluksessa (smoke-testi) |
| `image_folder` (Kuvakansio) | Valmis ja testattu, smoke-testi ok |
| `presentation_folder` (Presentaatiokansio) | Valmis ja testattu PDF:llä. LibreOffice/PowerPoint vain mock-testeillä |
| laulut | Ei aloitettu |

Smoke-testi ajettiin offscreen-tilassa (ei oikeaa näyttöä). Kaikki kolme pitää vielä kokeilla oikeassa GUI:ssa.

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
- Poisto kysyy vahvistuksen ja siirtää tiedostot roskakoriin (`QFile.moveToTrash`). `delete_item()` kutsutaan
  jokaiselle tiedostolle juuri ennen siirtoa, joten tiedosto on vielä olemassa (esitysten pikkukuvakansio lasketaan
  tiedoston sisällön hashista).
- Puun itemeissä `UserRole` = `Path`, `ItemTypeRole` (`UserRole + 1`) = `'folder'` / `'file'`.
- Aliluokka toteuttaa `is_supported_file()` ja `generate_slide_data()`. Lisäksi se voi ylikirjoittaa
  `load_item()`- ja `delete_item()`-metodit.
- `folder_files(kansio)` palauttaa kansion suoraan sisältämät tuetut tiedostot samassa järjestyksessä kuin puussa.
- `on_add_click()`: jos `single_service_item` on False, valittu kansio lisää jokaisen tiedostonsa Listaan erikseen.
- `create_item_from_id()` (remote-API) antaa tyypin vain juurikansion sisällä oleville poluille, joten remotella ei
  voi näyttää muita levyn tiedostoja.
- Remote-API hakee signaalit nimillä `<pluginin nimi>_go_live` ja `<pluginin nimi>_add_to_service`. Ne pitää
  määritellä aliluokassa juuri näillä nimillä (esim. `image_folder_go_live`), muuten remote-komennot kaatuvat.
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

### Image Folder -plugin: `openlp/plugins/image_folder/`

- Omat oletusasetukset: `image_folder/status`, `image_folder/background mode`, `image_folder/theme`.
- `ImageFolderTab` on `images`-pluginin `ImageTab`, joka lukee ja kirjoittaa `image_folder/*`-asetuksia.
- Pikkukuvat ovat kansiossa `<data>/image_folder/thumbnails`. Ydin etsii pluginin pikkukuvia sieltä, kun lista
  avataan tiedostosta. Tietokantaa ei ole, joten pikkukuvan nimi on kuvan *polun* sha256 (ei sisällön).
- Valitut kuvat ja kansiot (kansion suorat kuvat) tulevat yhdeksi kuvakohteeksi, jota voi toistaa silmukkana.
  Monivalinnan otsikko on pluginin monikkonimi.
- Taustan korvaus/palautus kuten `images`-pluginissa. Kuvake asetetaan itse ja `OnLoadUpdate` + `service_load()`
  palauttaa sen, kuten `media_folder`issa.

### Presentation Folder -plugin: `openlp/plugins/presentation_folder/`

- Käyttää `presentations`-pluginin ohjaimia (`*controller.py`), `PresentationTab`-asetussivua ja
  `MessageListener`-luokkaa. Ne ladataan samalla tavalla kuin vanhassa pluginissa (`extension_loader`).
- Ohjainasetukset (`presentations/Impress`, `presentations/override app` jne.) ovat yhteiset vanhan pluginin kanssa.
  Niiden oletusarvot ovat ytimessä valmiina.
- Ohjainten `thumbnail_folder` ja `temp_folder` vaihdetaan kansioon `<data>/presentation_folder/`, koska ydin kopioi
  palvelutiedoston pikkukuvat kansioon `<data>/<pluginin nimi>/thumbnails`.
- Slidecontroller lähettää viestit muotoon `<palvelukohteen nimi>_start` jne. `FolderMessageListener` rekisteröi ne
  nimellä `presentation_folder_*` (vanha kuuntelee `presentations_*`).
- Ydin korjaa tiedostosta avatun listan pikkukuvapolut vain nimelle `presentations` (`serviceitem.py`).
  `service_load()` tekee saman: palvelutiedoston suhteelliset polut muutetaan data-kansion absoluuttisiksi poluiksi.
- PDF (ja muut `PDF_CONTROLLER_FILETYPES`) näytetään Esityksessä ja esikatselussa kuvina, kuten vanhassa pluginissa
  (`service_item.name = 'images'`). Listassa se on komentokohde.
- `find_controller_by_type`, `populate_display_types` ja `clean_up_thumbnails` lainataan suoraan
  `PresentationMediaItem`-luokasta, koska ne eivät käytä tietokantaa.
- Kirjaston lataaminen ei avaa esityksiä, koska LibreOfficen tai PowerPointin käynnistys koko kansiolle olisi liian
  hidasta. Pikkukuva tulee näkyviin, kun esitys on kerran esikatseltu, näytetty tai lisätty Listaan. Kuvakkeet on
  välimuistissa tiedoston muokkausajan mukaan.
- Vanha ja uusi esitysplugin eivät saa olla päällä yhtä aikaa: kumpikin käynnistää omat ohjainprosessinsa.

### Vanhat pluginit pitää säilyttää asennettuina

Uudet pluginit eivät tarvitse vanhoja aktiivisiksi, mutta niiden pitää olla asennettuina:
`presentation_folder` ja `image_folder` tuovat niistä koodia. Lisäksi ytimen `ServiceItem.validate_item()` ja
slidecontroller tarkistavat State-nimen `media`, jonka vanha media-plugin rekisteröi myös pois päältä ollessaan.
Ilman sitä `media_folder`-kohteet merkitään listassa virheellisiksi.

### Suomennokset: `openlp/plugins/*/i18n/fi.ts`

- Käännökset ovat pluginien omissa tiedostoissa, eivät `resources/i18n/fi.ts`:ssä, jota upstream päivittää.
- `filesystem_library/i18n/fi.ts`: konteksti `OpenLP.FileSystemLibraryItem` sekä pohjaluokan käyttämät ytimen
  tekstit (`OpenLP.Ui` "Add folder" jne.), joista osa puuttuu ytimen suomennoksesta.
- `media_folder/i18n/fi.ts`: kontekstit `MediaFolderPlugin`, `MediaFolderPlugin.MediaItem` ja käytetyt
  `MediaPlugin.MediaItem`-tekstit.
- `image_folder/i18n/fi.ts`: `ImageFolderPlugin`, käytetyt `ImagePlugin.MediaItem`-tekstit sekä käsin lisätty
  `ImagesPlugin.ImageTab`, joka puuttuu ytimen suomennoksesta.
- `presentation_folder/i18n/fi.ts`: `PresentationFolderPlugin` ja käytetyt `PresentationPlugin.MediaItem`-tekstit.
  `PresentationTab`-asetussivun tekstit tulevat ytimen suomennoksesta.
- Termistö noudattaa olemassa olevaa suomennosta: service = "Lista", live = "Esitys", presentation =
  "Presentaatio" (ei "esitys", joka tarkoittaa livea).
- Päivitys lähdekoodin muututtua (esimerkki): `uv run pyside6-lupdate openlp/plugins/media_folder/*.py
  openlp/plugins/media_folder/lib/*.py -ts openlp/plugins/media_folder/i18n/fi.ts`. lupdate ei löydä ytimen
  `UiStrings`-tekstejä, joten `OpenLP.Ui`-konteksti on lisätty käsin.
- `.qm`-tiedostoja ei commitoida (`openlp/plugins/.gitignore`). Lähdekoodista ajettaessa käännä kaikki:
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

- Testit: `tests/openlp_plugins/{filesystem_library,media_folder,image_folder,presentation_folder}/`.
  Esitystestit käyttävät oikeaa PDF-ohjainta (QtPdf) ja valeohjainta muille muodoille. Valeohjain ei saa periä
  `PresentationController`-luokkaa, koska pluginit etsivät ohjaimet `__subclasses__()`-kutsulla.
- Smoke-testi oikealla sovelluksella: käynnistää OpenLP:n portable-tilassa kolmella pluginilla, lisää kuvia ja PDF:n
  Listaan ja Esitykseen, tallentaa ja avaa listan, sekä kokeilee remote-haun ja -liven. Tulostaa `SMOKE RESULT`:
  ```
  QT_QPA_PLATFORM=offscreen QTWEBENGINE_CHROMIUM_FLAGS=--no-sandbox \
      uv run python tests/openlp_plugins/smoke_filesystem_plugins.py <tyhjä työkansio>
  ```
  Suomen tekstit tarkistetaan vain, jos `.qm`-tiedostot on käännetty. Valmiin ini-tiedoston pitää sisältää
  `settings/version` ja `core/has run wizard`, muuten sovellus jää modaalidialogiin.
- Puhtaassa Linux-kontissa `uv sync` tarvitsee paketit `pkg-config libicu-dev libpq-dev` ja Qt/WebEngine
  `libegl1 libgl1 libxkbcommon0 libnss3 libxcomposite1 libxdamage1 libxrandr2 libxtst6 libasound2t64
  libfontconfig1 libdbus-1-3 libxkbfile1`.
- Testeissä oikeita widgettejä luotaessa `ActionList.shortcut_map` pitää tyhjentää testien välillä.
- Upstreamin `tests/openlp_core/lib/test_mediamanageritem.py` jättää `MediaManagerItem._setup`-patchin voimaan
  (`setup_patcher.stop` ilman sulkuja). Pluginien testipakettien `conftest.py` kutsuu siksi `patch.stopall()`.
  Uusiin testipaketteihin, jotka luovat oikeita media manager -itemejä, tarvitaan sama fixture.
- `uv run` / `uv sync` muuttaa `uv.lock`-tiedostoa (lisää `packaging`). Palauta se, ellei muutosta tarkoiteta.
- Käytä tiedostoissa samaa GPL-lisenssiotsikkoa kuin muualla koodissa.

## Seuraavaksi

Uudet pluginit tehdään samalla mallilla kuin `media_folder`: oletusasetukset, käännökset, kuvakkeet ja testit
pluginin omassa hakemistossa, ei ytimessä.

1. Kokeile `media_folder`, `image_folder` ja `presentation_folder` oikeassa GUI:ssa, esitykset myös LibreOfficella
   ja PowerPointilla.
2. Lauluplugin. Ehdotus: OpenLyrics-XML-tiedostot kansiossa. Nykyinen `OpenLyrics.xml_to_song` on sidottu
   tietokantaan (`self.manager`), joten tarvitaan kevyt jäsennin, joka ei käytä tietokantaa. Muokkausnäkymä
   (`editsongform.py`) on myös tietokantasidonnainen. Vanhan pluginin OpenLyrics-viennillä laulut saa tiedostoiksi.
   Ytimen remote-API:n sävellajin vaihto toimii vain nimellä `songs`.
3. Omat diat (`custom`) tarvittaessa, esim. tekstitiedostoina kansiossa.
