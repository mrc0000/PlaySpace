# Attribution & Provenance

## Source data

This archive indexes records from two public U.S. government surfaces released
on **May 8, 2026** as part of the UAP disclosure:

- **U.S. Department of War — UAP portal**: <https://www.war.gov/UFO/>
- **U.S. National Archives — Record Group 615 (UAP)**: <https://www.archives.gov/research/topics/uaps/rg-615>
  - FAA — NAID [493468575](https://catalog.archives.gov/id/493468575)
  - U.S. Nuclear Regulatory Commission — NAID [488808322](https://catalog.archives.gov/id/488808322)
  - Office of the Director of National Intelligence — NAID [493468579](https://catalog.archives.gov/id/493468579)
  - National Security Agency — NAID [580103959](https://catalog.archives.gov/id/580103959)
  - Department of State — NAID [608806625](https://catalog.archives.gov/id/608806625)

Per object, the manifest records `object_url` (the original government URL),
`naid`, `agency`, and `captured_at`. These fields preserve direct provenance
back to the canonical source. Treat the source URL as authoritative; treat
the manifest as a snapshot.

## Copyright

Records in RG-615 and on war.gov are works of the United States federal
government. Under **17 U.S.C. § 105**, works prepared by an officer or
employee of the U.S. government as part of their official duties are not
subject to copyright in the United States and are in the public domain.

This project (`uap-archive`) adds no copyright. All code and manifests in
this repository are released under [CC0-1.0](./LICENSE).

## Contact

The User-Agent used by this tool when contacting NARA and war.gov includes
a contact line so administrators can reach the maintainer. To set yours:

```bash
git config user.email you@example.com
```

The User-Agent string built at runtime is:

```
UAP-Archive/<version> (+<repo-url>; mailto:<git-config-email>) httpx/<v>
```

If you operate one of the source services and want this client to throttle
further, slow down, or stop entirely, please open an issue on the repo or
email the contact in the User-Agent. We honor `Retry-After` and respect
`robots.txt`.
