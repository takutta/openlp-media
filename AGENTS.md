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
| `song_folder` (Laulukansio) | Valmis ja testattu: muokkaus, uusi laulu, songs-asetukset, taustamusiikki, teema, transponointi, indeksin välimuisti. Smoke-testi ok |

Smoke-testi ajettiin offscreen-tilassa (ei oikeaa näyttöä). Kaikki pitää vielä kokeilla oikeassa GUI:ssa.

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
- `related_files(tiedosto)` (oletus tyhjä) palauttaa tiedostoon kuuluvat tiedostot, jotka eivät näy puussa (esim.
  laulun äänitiedosto). Ne kopioidaan, siirretään ja siirretään roskakoriin tiedoston mukana. Mitään ei
  ylikirjoiteta: jos kohteessa on jo samanniminen tiedosto, se jätetään paikalleen ja käyttäjälle kerrotaan.
- `folder_files(kansio)` palauttaa kansion suoraan sisältämät tuetut tiedostot samassa järjestyksessä kuin puussa.
- `on_add_click()`: jos `single_service_item` on False, valittu kansio lisää jokaisen tiedostonsa Listaan erikseen.
- `create_item_from_id()` (remote-API) antaa tyypin vain juurikansion sisällä oleville poluille, joten remotella ei
  voi näyttää muita levyn tiedostoja.
- Remote-API hakee signaalit nimillä `<pluginin nimi>_go_live` ja `<pluginin nimi>_add_to_service`. Ne pitää
  määritellä aliluokassa juuri näillä nimillä (esim. `image_folder_go_live`), muuten remote-komennot kaatuvat.
- Jos aliluokka asettaa `has_edit_icon`-arvon, kontekstivalikkoon tulee "Muokkaa" (`on_edit_click`).
- `_get_tree_item(item)` muuntaa `generate_slide_data()`:lle annetun arvon (None / `QModelIndex` / item) puun
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
  (normalisoitu: pienet kirjaimet, ei välimerkkejä, sointuja eikä muotoilutageja).
  - Välimuisti: `load()`/`save()` lukevat ja kirjoittavat indeksin JSON-tiedostoon `<data>/song_folder/index.json`
    (mediaitemin `initialise()` lataa, `reload()` tallentaa, jos `changed`). Rikkinäinen tai vanhan version
    (`CACHE_VERSION`) välimuisti ohitetaan. Kasvata `CACHE_VERSION`ia, kun `FileSong` tai hakuteksti muuttuu.
  - Indeksiä käytetään vain puun nimiin ja hakuun. `generate_slide_data()` jäsentää tiedoston aina uudelleen,
    jotta slidet ovat ajan tasalla ja laulun omat muotoilutagit rekisteröityvät (välimuistista luettu laulu ei
    rekisteröi niitä).
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
  - songs-pluginin asetukset (`songs/*`) ovat yhteiset: isot kirjaimet (`{uc}`), ensimmäinen slide (laulukirjat
    `O1` tai alatunniste `O2`) ja seuraavan rivin esikatselu (`{preview}`, säetyypeittäin `PREVIEW_SETTINGS`)
    toimivat kuten songs-pluginissa. Plugin käyttää asetussivunaan songs-pluginin `SongsTab`-luokkaa. Jos
    molemmat pluginit ovat päällä, sama asetussivu näkyy kahdesti. Sivulla on myös asetuksia, joilla ei ole
    vaikutusta laulukansioon (SongSelect, "update service on edit", "add song from service").
  - Taustamusiikki: laulun vieressä oleva samanniminen äänitiedosto (`Laulu.mp3` tiedostolle `Laulu.xml`,
    `get_supported_media_suffix()`-äänipäätteet). Vaatii State-nimen `media`. `songs/auto play audio` toimii
    ytimessä. Jos samannimisiä äänitiedostoja on useita, ensimmäinen soitetaan. Äänitiedostot ovat laulun
    `related_files()`, joten ne kopioituvat, siirtyvät ja poistuvat laulun mukana.
  - Lomakkeen välilehdellä "Taustamusiikki" voi valita äänitiedoston tai poistaa sen. Tallennettaessa
    (`save_background_audio()`) valittu tiedosto kopioidaan laulun viereen laulun nimellä, ja laulun muut
    äänitiedostot siirretään roskakoriin. Jos taustamusiikkia ei muutettu, mitään ei tehdä. Uusi laulu ei koske
    valmiiksi samannimisiin äänitiedostoihin, ellei ääntä valittu. Jos vaihto epäonnistuu, laulu on silti
    tallennettu ja käyttäjälle kerrotaan.
  - Teema: OpenLyricsissä ei ole teemaa, joten se on tiedostossa omassa nimiavaruudessaan
    `<openlp:theme xmlns:openlp="http://openlp.org/ns/song-folder">Nimi</openlp:theme>` (`songfile.THEME_TAG`).
    Muut ohjelmat ohittavat sen. Tyhjä teema = oletus.
- Plugin rekisteröi `song_folder/status`-oletusasetuksen ja songs-pluginin `song_footer`-oletuksen, joten
  alatunniste toimii, vaikka songs-plugin olisi pois päältä.
- `lib/songwriter.py`: `song_to_xml(laulu, alkuperäinen)` ja `write_song_file(laulu, polku, keep_contents)`
  kirjoittavat OpenLyrics 0.9:ää ilman tietokantaa. Tiedosto yhdistettiin kahden rinnakkaisen session toteutuksista.
  - Olemassa olevasta tiedostosta korvataan vain muokattavat ominaisuudet (`EDITED_PROPERTIES`: nimet, tekijät,
    copyright, CCLI, säejärjestys, laulukirjat, aiheet, kommentit) sekä `<lyrics>`. Ne korvataan omille paikoilleen,
    ja uudet lisätään skeeman järjestyksessä (`PROPERTY_ORDER`). Kaikki muu säilyy järjestyksessään: tempo,
    sävellaji, julkaisija, `<song>`-attribuutit (`createdIn`, `chordNotation`…), vieraat elementit ja tiedoston omat
    muotoilutagit (myös käyttämättömät). Sanoitusten käyttämät uudet tagit lisätään. Säkeiden `<comment>`-elementit
    ja säkeiden omat attribuutit (paitsi `lang`) eivät säily, koska `<lyrics>` kirjoitetaan uudelleen.
  - Tiedosto ilman OpenLyrics-nimiavaruutta siirretään nimiavaruuteen. Rikkinäinen tai muu kuin laulutiedosto
    kirjoitetaan alusta.
  - Sanoitusten muunnos (soinnut, muotoilutagit, `[---]`, `[--}{--]`) tehdään songs-pluginin `OpenLyrics`-
    apumetodeilla, joten tulos on sama kuin songs-pluginin viennissä. Säkeen lopussa oleva `[---]` jätetään pois.
  - Tiedosto sisennetään, mutta `<lines>`-elementtien sisältöä ei, koska muut ohjelmat lukevat sen välilyönnit
    tekstinä.
  - Kirjoitus tehdään piilotettuun väliaikaistiedostoon samaan kansioon ja vaihdetaan `os.replace`illa, joten
    epäonnistunut tallennus ei riko vanhaa tiedostoa. Virheet nostavat `SongFileError`in. Vanhan tiedoston oikeudet
    säilyvät, ja uusi saa tavalliset oikeudet (umask).
  - `song_file_name(otsikko, kansio)` tekee uudelle laululle tiedostonimen otsikosta (kielletyt merkit → `_`) ja
    lisää tarvittaessa ` (2)`, ` (3)`… Mitään ei ylikirjoiteta.
  - Testi `test_resource_files_survive_a_round_trip` varmistaa, että songs-pluginin OpenLyrics-testitiedostot
    säilyvät samoina, kun ne kirjoitetaan uudelleen.
- `forms/editsongform.py`: `SongFileEditForm` on oma, kevyempi lomake (vanha on tietokantasidonnainen).
  - Sanat muokataan yhtenä tekstinä, jossa jokaisen säkeen alussa on rivi `---[Säe:1]---`. Muoto on sama kuin
    songs-pluginin "Muokkaa kaikkia" -näkymässä. Muodot `---[Kertosäe:1:en]---` (kieli) ja `---[Säe:1a]---` (osa)
    toimivat myös. Säetyypin voi kirjoittaa suomeksi, englanniksi tai lyhenteenä. Ensimmäistä merkintää edeltävä
    teksti on säe 1. Samannimiset säkeet yhdistetään kuten luettaessa.
  - Säejärjestys näytetään käännetyillä tunnuksilla (`S1 K1`) ja luetaan sekä käännetyillä että englanninkielisillä.
  - Tekijät on listassa tyyppeineen. Aiheet ja laulukirjat (`Kirja #12`) kirjoitetaan yksi riville.
  - Teema valitaan teemaluettelosta (`theme_manager.get_theme_names()`, päivittyy `theme_update_list`-
    tapahtumasta). Transponointi ylös/alas (`transpose_lyrics`) näkyy, kun `songs/enable chords` on päällä.
  - Tekstit ovat songs-pluginin konteksteista (`SongsPlugin.EditSongForm` jne.), joten suurin osa suomennoksesta
    tulee ytimestä.
- Muokkaus mediaitemissä:
  - "Uusi" kirjoittaa laulun valittuun kansioon ja "Muokkaa" (myös kontekstivalikossa) valittuun tiedostoon.
    Tiedostonimi ei muutu, vaikka otsikko muuttuisi. Muokattu laulu päivitetään myös Listaan
    (`replace_service_item`) aina, toisin kuin songs-pluginissa, jossa se riippuu `songs/update service on edit`
    -asetuksesta.
  - Palvelukohteella on `CanEdit`, ja `edit_id` on tiedostopolku. Tällöin Listan ja esikatselun "Muokkaa" toimivat
    (`on_remote_edit`, vain kirjaston sisällä oleville tiedostoille). `edit_id` ei tallennu listatiedostoon, joten
    `service_load()` palauttaa sen `data_string['file path']`-arvosta, jos tiedosto on yhä olemassa. Muuten
    `CanEdit` poistetaan.
  - Jos tiedosto muuttuu levyllä muokkauksen aikana, ohjelma kysyy ennen ylikirjoitusta. Jos tallennus epäonnistuu,
    lomake avautuu uudelleen sisältö tallessa. Tallennuksen jälkeen indeksistä poistetaan tiedoston vanha tieto,
    koska koko ja aikaleima voivat olla samat.
- Puuttuu vielä:
  - Säkeen muokkaus erillisessä dialogissa (songs-pluginin `EditVerseForm`). Lomakkeen yksi tekstikenttä kattaa
    saman, joten tätä ei ehkä tarvita.
  - Remote-API:n transponointi (`/api/v2/plugins/songs/transpose-live-item`) ei toimi, koska ydin tarkistaa
    nimen (`name != 'songs'`). Sama tilanne kuin media_folderin play/pause-kutsuissa.

### Vanhat pluginit pitää säilyttää asennettuina

Uudet pluginit eivät tarvitse vanhoja aktiivisiksi, mutta niiden pitää olla asennettuina:
`presentation_folder`, `image_folder` ja `song_folder` tuovat niistä koodia. Lisäksi ytimen
`ServiceItem.validate_item()` ja slidecontroller tarkistavat State-nimen `media`, jonka vanha media-plugin rekisteröi myös pois päältä ollessaan.
Ilman sitä `media_folder`-kohteet merkitään listassa virheellisiksi.

### Suomennokset: `openlp/plugins/*/i18n/fi.ts`

- Käännökset ovat pluginien omissa tiedostoissa, eivät `resources/i18n/fi.ts`:ssä, jota upstream päivittää.
- `filesystem_library/i18n/fi.ts`: konteksti `OpenLP.FileSystemLibraryItem` sekä pohjaluokan käyttämät ytimen
  tekstit (`OpenLP.Ui` "Add folder" jne.), joista osa puuttuu ytimen suomennoksesta.
- `media_folder/i18n/fi.ts`: kontekstit `MediaFolderPlugin`, `MediaFolderPlugin.MediaItem` ja käytetyt
  `MediaPlugin.MediaItem`-tekstit.
- `song_folder/i18n/fi.ts`: kontekstit `SongFolderPlugin`, `SongFolderPlugin.MediaItem` sekä alatunnisteen
  `OpenLP.Ui`- ja `SongsPlugin.MediaItem`-tekstit. Tekijätyyppien nimet (`SongsPlugin.AuthorType`) tulevat ytimen
  suomennoksesta. Lomakkeen käyttämät `SongsPlugin.EditSongForm`-tekstit on kopioitu ytimen suomennoksesta.
  `SongsPlugin.EditVerseForm` ("Pakotettu jako") on lisätty käsin, koska se puuttuu ytimestä eikä lupdate löydä
  `UiStrings`-tekstejä. lupdate merkitsee käsin lisätyt viestit vanhentuneiksi (`vanished`), joten tarkista ne
  päivityksen jälkeen.
- `image_folder/i18n/fi.ts`: `ImageFolderPlugin`, käytetyt `ImagePlugin.MediaItem`-tekstit sekä käsin lisätty
  `ImagesPlugin.ImageTab`, joka puuttuu ytimen suomennoksesta.
- `presentation_folder/i18n/fi.ts`: `PresentationFolderPlugin` ja käytetyt `PresentationPlugin.MediaItem`-tekstit.
  `PresentationTab`-asetussivun tekstit tulevat ytimen suomennoksesta.
- Termistö noudattaa olemassa olevaa suomennosta: service = "Lista", live = "Esitys", presentation =
  "Presentaatio" (ei "esitys", joka tarkoittaa livea).
- Päivitys lähdekoodin muututtua (esimerkki): `uv run pyside6-lupdate openlp/plugins/media_folder/*.py
  openlp/plugins/media_folder/lib/*.py -ts openlp/plugins/media_folder/i18n/fi.ts`. lupdate ei löydä ytimen
  `UiStrings`-tekstejä, joten `OpenLP.Ui`-konteksti on lisätty käsin. song_folderissa mukaan myös
  `openlp/plugins/song_folder/forms/*.py`.
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

- Testit: `tests/openlp_plugins/{filesystem_library,media_folder,image_folder,presentation_folder,song_folder}/`.
  Esitystestit käyttävät oikeaa PDF-ohjainta (QtPdf) ja valeohjainta muille muodoille. Valeohjain ei saa periä
  `PresentationController`-luokkaa, koska pluginit etsivät ohjaimet `__subclasses__()`-kutsulla.
- Smoke-testi oikealla sovelluksella: käynnistää OpenLP:n portable-tilassa neljällä pluginilla, lisää kuvia, PDF:n
  ja laulun Listaan, muokkaa laulua oikealla lomakkeella, tallentaa ja avaa listan, sekä kokeilee remote-haun ja
  -liven. Tarkistukset alkavat, kun pluginit ovat valmiina. Tulostaa `SMOKE RESULT`:
  ```
  QT_QPA_PLATFORM=offscreen QTWEBENGINE_CHROMIUM_FLAGS=--no-sandbox \\
      uv run python tests/openlp_plugins/smoke_filesystem_plugins.py <tyhjä työkansio>
  ```
  Suomen tekstit tarkistetaan vain, jos `.qm`-tiedostot on käännetty. Valmiin ini-tiedoston pitää sisältää
  `settings/version` ja `core/has run wizard`, muuten sovellus jää modaalidialogiin.
- Puhtaassa Linux-kontissa `uv sync` tarvitsee paketit `pkg-config libicu-dev libpq-dev` ja Qt/WebEngine
  `libegl1 libgl1 libxkbcommon0 libnss3 libxcomposite1 libxdamage1 libxrandr2 libxtst6 libasound2t64
  libfontconfig1 libdbus-1-3 libxkbfile1`.
- Laulun lukeminen voi lisätä globaaliin `FormattingTags.html_expands`-listaan väliaikaisia tageja, mikä rikkoo
  songs-pluginin testin `test_process_formatting_tags`. `song_folder/conftest.py` palauttaa listan jokaisen
  testin jälkeen.
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

1. Kokeile kaikkia uusia plugineja oikeassa GUI:ssa, esitykset myös LibreOfficella ja PowerPointilla. Tätä ei voi
   tehdä pilvikontissa.
2. Laulukansion pienet puutteet (ks. "Puuttuu vielä" yllä).
3. Omat diat (`custom`) tarvittaessa, esim. tekstitiedostoina kansiossa.
4. Ytimen nimitarkistukset (media play/pause/stop, laulujen transponointi remote-API:ssa) voisi ehdottaa
   upstreamiin. Ytimeen ei tehdä muutoksia tässä forkissa.
