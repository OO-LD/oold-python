# CHANGELOG

All notable changes to this project are documented here. Versions are cut
automatically from Conventional Commits on every merge to main by
[python-semantic-release](https://python-semantic-release.readthedocs.io/). Do
not edit released sections by hand.

<!-- version list -->

## v0.16.4 (2026-08-06)

### Bug Fixes

- Register a class only under the type IRIs it introduces
  ([`7ca1b85`](https://github.com/OO-LD/oold-python/commit/7ca1b85e37ed93ca2447ececfa11dc11a2265283))

### Chores

- License fix
  ([`daa8d8c`](https://github.com/OO-LD/oold-python/commit/daa8d8cfa325a3745c851c845b9fae7b5e51a0cc))

### Continuous Integration

- **release**: Add whats-changed notes with changelog link for zenodo
  ([`147d70f`](https://github.com/OO-LD/oold-python/commit/147d70fbf1c5da070f3cb9055fbe96e831fe8eaa))

- **release**: Update on title and authors
  ([`996c4de`](https://github.com/OO-LD/oold-python/commit/996c4dee6b4f07b6ec994e87cb341155a12e955c))


## v0.16.3 (2026-07-29)

### Bug Fixes

- Correct resolve_iri typo to resolve_iris in WikiDataSparqlResolver
  ([`d04108a`](https://github.com/OO-LD/oold-python/commit/d04108abb74387a1af1aea9db62e4eac1298a722))

- Restore tag-push release trigger; rewrite CONTRIBUTING for clarity and brevity
  ([`1b3436b`](https://github.com/OO-LD/oold-python/commit/1b3436b545b933520c8ea2cf7dc099635218ddce))

- **ci**: Disable uv cache in benchmark job to prevent post-step failure
  ([`c5873ed`](https://github.com/OO-LD/oold-python/commit/c5873edb6b3a39f43a5281a543cd62268e26b7f8))

- **ci**: Use git worktree for baseline benchmarks to avoid branch switch
  ([`5139d76`](https://github.com/OO-LD/oold-python/commit/5139d76e0f0a4a634d6426fe7a3edd94c86c99fd))

### Build System

- Map module names for optional UI extras to silence deptry warnings
  ([`d963a13`](https://github.com/OO-LD/oold-python/commit/d963a13265c07084782ffeb2cf9dcfb8bda228f3))

- Migrate from pyscaffold/setuptools to hatchling + uv tooling
  ([`9ce1f13`](https://github.com/OO-LD/oold-python/commit/9ce1f1335b9f408c837d88a54d92b65b0527e6b0))

### Chores

- Authorship for zenodo releases through CITATION.cff file; Guideline on contributing and docs
  updated with how to be author on zenodo
  ([`ff73bc0`](https://github.com/OO-LD/oold-python/commit/ff73bc063afcabd27aa3b564ddcce08d96640b5d))

- Ignore local files
  ([`bf1a9e0`](https://github.com/OO-LD/oold-python/commit/bf1a9e093d58a13436316eb6d09d3c73599a82e1))

- **release**: Seed version fields and changelog for psr
  ([`df5f4a8`](https://github.com/OO-LD/oold-python/commit/df5f4a8ae97ede104826df6f32fe9d8d1ee2a517))

### Continuous Integration

- Add conventional-commit commit-msg hook
  ([`d263194`](https://github.com/OO-LD/oold-python/commit/d263194ab0c428fdd27e88e680f75c61fe380472))

- Add semantic-release version preview on pull requests
  ([`75a2998`](https://github.com/OO-LD/oold-python/commit/75a29981387b91e3f8934fc515e6865367efcb22))

- Fix version-preview to show bump and changelog, v-prefixed and reworded
  ([`4db8800`](https://github.com/OO-LD/oold-python/commit/4db8800177b077610543dea1c7d3120ac8b31dfa))

- Make version-preview evaluate on main so PR bump shows correctly
  ([`92d4101`](https://github.com/OO-LD/oold-python/commit/92d410104d539236b4fc34bb7a5b02925ab98a81))

- **release**: Automate release on merge to main via psr
  ([`5ddafe7`](https://github.com/OO-LD/oold-python/commit/5ddafe7d850717acb4e353f406e4b592ab27add4))

- **release**: Configure python-semantic-release (psr) with static version
  ([`b81a511`](https://github.com/OO-LD/oold-python/commit/b81a511801ff25046b688f9a776ba1733aecdb04))

- **release**: Push release commit via github app token to satisfy branch ruleset
  ([`2e64068`](https://github.com/OO-LD/oold-python/commit/2e640683a819a0a4261ff2e635e15f09ae081284))

### Documentation

- Add landing hero on Home, move old content to new About page
  ([`32d22b5`](https://github.com/OO-LD/oold-python/commit/32d22b5041105f870546bae5021fb3eb5ad29b60))

- Add OO-LD logo, fix tab/icon rendering, uv-first install, tidy README
  ([`9404a1d`](https://github.com/OO-LD/oold-python/commit/9404a1d092e6eb8f354c12fd80e8891c3fe0b30e))

- Add tabs nav + logo + landing hero, fix page title, tidy README
  ([`e16d80c`](https://github.com/OO-LD/oold-python/commit/e16d80c73721b2fd972aa8bd75c919840a00106b))

- Drop redundant Development page (merged into Contributing)
  ([`6c929c2`](https://github.com/OO-LD/oold-python/commit/6c929c2fbf922e0b2d351b22197b7c549b7984eb))

- Fix + enlarge mermaid diagrams, hide footer on landing page
  ([`c87a92d`](https://github.com/OO-LD/oold-python/commit/c87a92ddd6fc93cc87e8abff15131ab0e930b7b7))

- Fix home hero right-side gap and top alignment
  ([`c6a9d0b`](https://github.com/OO-LD/oold-python/commit/c6a9d0bfcf1a9253281361f805032040b74b927e))

- Fix landing hero gradient — seamless yellow to bottom, no footer
  ([`b6cc144`](https://github.com/OO-LD/oold-python/commit/b6cc14436422e22f6a7c7fad92781fbb3de4927f))

- Fix raw tab artifacts (enable pymdownx.tabbed), lead with uv install
  ([`73ecc54`](https://github.com/OO-LD/oold-python/commit/73ecc54e15a87f7170c5abd1f8ac6a315a04e4c0))

- Reformat for markdownlint, add AI statement
  ([`50ffbed`](https://github.com/OO-LD/oold-python/commit/50ffbed8c1e7bbbe522e61d44e95dd714c7aad7b))

- Regenerate documentation and add citation support
  ([`d88f913`](https://github.com/OO-LD/oold-python/commit/d88f91382ba3ac4881ef0ddcee2056da69cbf238))

- Rm authors entirely to make use of auto contributor fetching from github (bots should be already
  ignored)
  ([`6446a91`](https://github.com/OO-LD/oold-python/commit/6446a919ed7700ad107bb1d99d0b8b78561026f1))

- Upd ai guidelines
  ([`bdfc192`](https://github.com/OO-LD/oold-python/commit/bdfc1925a354f0b1e20910e3b67274d498d46326))

- **contributing**: Document conventional commits and auto-release
  ([`cfaa811`](https://github.com/OO-LD/oold-python/commit/cfaa811a9b8529fc17ff8da2c164b7606891d617))
