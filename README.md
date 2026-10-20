# Lecteur CD Web — version Docker

Lecture à distance de CD audio dans le navigateur, avec piste précédente, lecture, pause, suivante, arrêt, recherche MusicBrainz, **éjection** et **fermeture** du tiroir.

## Démarrage sous Ubuntu / CasaOS / ZimaOS / UmbrelOS

Prérequis : Docker et le plugin Docker Compose, lecteur accessible en `/dev/sr0`.

```sh
cd lecteur-cd-docker
docker compose up -d --build
```

Ouvrir **http://ADRESSE-IP-DU-SERVEUR:8095**.

Pour suivre les journaux :

```sh
docker compose logs -f
```

Pour connaître le périphérique : `ls -l /dev/sr* /dev/sg*`.

Si le lecteur n'est pas `/dev/sr0`, modifier **à la fois** la source de `devices:` et `CD_DEVICE`. Certains lecteurs USB/Blu-ray peuvent demander la correspondance additionnelle de leur périphérique `/dev/sgX` dans `devices:`. Le périphérique `/dev/sgX` peut changer après un redémarrage.

**Attention :** une seule application doit utiliser le CD à la fois. Sur l'OptiPlex actuel, arrêter l'ancien `lecteur-cd.service` pour libérer le port 8095 et le périphérique : `sudo systemctl stop lecteur-cd.service` ; ne le désactiver qu'une fois la version Docker validée : `sudo systemctl disable lecteur-cd.service`.

### Notes
- Le flux est généré en MP3 320 kb/s à la volée à partir de `cdparanoia` et de FFmpeg.
- La pause fonctionne dans le navigateur. Les sauts à un point précis d'une piste ne sont pas pris en charge.
- L'ouverture/fermeture du tiroir dépend des capacités du lecteur matériel ; certains lecteurs n'acceptent pas la fermeture logicielle.
- MusicBrainz a besoin d'un accès Internet mais la lecture du disque fonctionne sans lui.
- Pas d'authentification : n'exposer le port **que sur le réseau local**, pas sur Internet.
- Si un ancien processus accède au lecteur, l'éjection peut échouer avec « device busy ».
- Cette version est une reconstitution autonome de la V6, pas une copie bit à bit du script d'origine.
