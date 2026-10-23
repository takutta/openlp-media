# AGENTS.md

## Projekti

OpenLP:n fork, johon tehdään uudet media-, kuva- ja laulupluginit vanhojen pohjalta. Uudet pluginit käyttävät
suoraa tiedostopolkua tietokannan sijaan: valittu kansio levyllä *on* kirjasto.

- Upstream: `https://gitlab.com/openlp/openlp.git` (remote `upstream`; OpenLP ei ole GitHubissa).
- Origin: `takutta/openlp-media` (GitHub, private).
- Työhaara: `feature/filesystem-plugins`. Upstreamin `master` on yhdistetty siihen (`--allow-unrelated-histories`).
- Vanhat pluginit (`media`, `images`, `songs`) jätetään ennalleen; uudet tehdään niiden rinnalle.

## Tila

| Plugin | Tila |
| --- | --- |
| `media_folder` (Mediakansio) | Valmis ja testattu, ei vielä kokeiltu oikeassa GUI:ssa |
| kuvat | Ei aloitettu |
| laulut | Ei aloitettu |

Mitään ei ole vielä commitoitu.

## Mitä on tehty

### Yhteinen pohjaluokka: `openlp/core/ui/filesystemlibrary.py`

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
- Luokka rekisteröi itse oletusasetukset (`root folder`, `last directory` ja listanäkymän pikanäppäimet
  `shortcuts/listView<Name>…`). Muuten `create_widget_action` kaatuu KeyErroriin.

### Media Folder -plugin: `openlp/plugins/media_folder/`

- Pluginin nimi on `media_folder`. Nimen täytyy vastata `de_hump(MediaFolderPlugin)`-muotoa, koska `State`
  hakee pluginia nimellä `<nimi>_plugin`.
- Listaa ääni- ja videotiedostot `get_supported_media_suffix()`-funktion perusteella, kirjainkoosta
  riippumatta.
- Kansion lisääminen palveluun lisää jokaisen sen mediatiedoston erikseen.
- Verkko- ja laitestriimit jätettiin pois, koska niillä ei ole tiedostopolkua.

### Pienet muutokset ytimeen

- `openlp/core/common/settings.py`: `media_folder/status`.
- `openlp/core/lib/serviceitem.py`: kuvake myös `media_folder`-palvelukohteille.
- `openlp/core/ui/media/remote.py`: remote-API:n play/pause/stop hyväksyy myös `media_folder`-kohteet.
- `tests/openlp_core/lib/test_mediamanageritem.py`: korjattu upstreamin bugi (`setup_patcher.stop` ilman sulkuja
  jätti patchin voimaan muihin testeihin).

### Suomennos: `resources/i18n/fi.ts`

- Uudet kontekstit `OpenLP.FileSystemLibraryItem`, `MediaFolderPlugin` ja `MediaFolderPlugin.MediaItem`.
  Lisäksi täydennetty kolme puuttuvaa jaettua tekstiä ("Lisää kansio" jne.).
- Termistö noudattaa olemassa olevaa suomennosta: service = "Lista", live = "Esitys".
- Tiedosto on LF-muotoinen. Samanniminen konteksti (esim. `OpenLP.Ui`) esiintyy tiedostossa useasti.
- `.qm`-tiedostoja ei commitoida. Lähdekoodista ajettaessa:
  `uv run pyside6-lrelease resources/i18n/fi.ts -qm resources/i18n/fi.qm`

## Kehitys

```
uv sync --all-extras
QT_QPA_PLATFORM=offscreen uv run pytest tests -q
uv run flake8 <tiedostot>      # rivin maksimipituus 120
uv run python run_openlp.py
```

- Testit: `tests/openlp_core/ui/test_filesystemlibrary.py` ja `tests/openlp_plugins/media_folder/`.
- Testeissä oikeita widgettejä luotaessa `ActionList.shortcut_map` pitää tyhjentää testien välillä.
- `uv run` / `uv sync` muuttaa `uv.lock`-tiedostoa (lisää `packaging`). Palauta se, ellei muutosta tarkoiteta.
- Käytä tiedostoissa samaa GPL-lisenssiotsikkoa kuin muualla koodissa.

## Seuraavaksi

1. Kuvaplugin `FileSystemLibraryItem`-luokan päälle (pikkukuvat, taustan korvaus ja teema-asetukset
   `images`-pluginista).
2. Lauluplugin. Ehdotus: OpenLyrics-XML-tiedostot kansiossa. Nykyinen `OpenLyrics.xml_to_song` on sidottu
   tietokantaan (`self.manager`), joten tarvitaan kevyt jäsennin, joka ei käytä tietokantaa. Muokkausnäkymä
   (`editsongform.py`) on myös tietokantasidonnainen.
