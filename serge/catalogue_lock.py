#!/usr/bin/env python3
"""SHA figés du catalogue (fichiers + sous-objets). Maj = test rouge sinon."""

from __future__ import annotations

# (kind, id) → files_sha. Contenu des fichiers seulement, puis compose.
SHA_ATTENDUS: dict[tuple[str, str], str] = {
    (
        'canal',
        'email',
    ): 'cc757e2fd186880b8c39b6c84e8819a62e79ac257c87dabdfa687a95965b291f',
    (
        'canal',
        'voice',
    ): 'cdfc6e7351890d553232d2b571d503b5cab4d7c4929076c94448556a66e2f367',
    (
        'etape',
        'build_venture',
    ): '84a703bab885c170ecd7cbeeee3177d85db4fa9d053a857e5a248610cd38999a',
    (
        'etape',
        'caisse',
    ): '52c4c17ca9b5cded964ddd82d6340eb956fe4e7c356203cc83d2d60ee3732fa0',
    (
        'etape',
        'choix_venture',
    ): 'b5909b772f1e2ba54ebdc9223f760247751ad972b9526fb0b6d655add8c2a7b0',
    (
        'etape',
        'collect_feedback',
    ): 'ee3d84d234be80e9320b225685b78181b1cd82f24edaf5fd514f06c19742f6a3',
    (
        'etape',
        'conception_poc',
    ): '43a0803f7839f557149b5cdcd6beb7f1dbf9ea013bb92fce6635dfb1505e6580',
    (
        'etape',
        'pre_prospection',
    ): 'f0654b60457b5530e7c0d0a59d717dd3683d0cae48a92d9d89eafae6e614b7f5',
    (
        'etape',
        'prospection_light',
    ): 'a3405221ce210b2c60b563af05d78ebc6afe9ed94ee5da3449465a94ba3d43fe',
    (
        'etape',
        'prospection_lourde',
    ): 'a96ffd01b66357b22b56b01ad6275e6e5b53666776f2fd3ff76a6a882437297e',
    (
        'lien',
        'build-lourde',
    ): '40f272829674ebc13a0e2a9001f6765b8396b4178b6dc159028fb691e5c0b1df',
    (
        'lien',
        'choix-build',
    ): '40f272829674ebc13a0e2a9001f6765b8396b4178b6dc159028fb691e5c0b1df',
    (
        'lien',
        'light-choix',
    ): '40f272829674ebc13a0e2a9001f6765b8396b4178b6dc159028fb691e5c0b1df',
    (
        'lien',
        'lourde-caisse',
    ): '40f272829674ebc13a0e2a9001f6765b8396b4178b6dc159028fb691e5c0b1df',
    (
        'lien',
        'lourde-feedback',
    ): '40f272829674ebc13a0e2a9001f6765b8396b4178b6dc159028fb691e5c0b1df',
    (
        'lien',
        'poc-light',
    ): '40f272829674ebc13a0e2a9001f6765b8396b4178b6dc159028fb691e5c0b1df',
    (
        'lien',
        'pre-poc',
    ): '40f272829674ebc13a0e2a9001f6765b8396b4178b6dc159028fb691e5c0b1df',
    (
        'llm',
        'build_artifact',
    ): '918d807c491659057b1bbc886db0c412e997c24bd3e253c191662ee22aa05bba',
    (
        'llm',
        'classify_owner_intent',
    ): '01826b8f4db329628ed1645466d8e44ad8795a671eaa747f59f776c70e907d94',
    (
        'llm',
        'classify_reply',
    ): 'b06aa1e4c79d37bed56ad9d065debd450d440dfe4ef1b956af4dfc0bb273cec5',
    (
        'llm',
        'cluster_demand',
    ): '22889ca79103f260bc9deed6d2aab9300bf963da613fcf1b070fe26b9a614c30',
    (
        'llm',
        'listen_choose_poc',
    ): '03f92156c22b6624581c0afbd33f4a122b4b571e11d65a757dfc402e1b2b2e61',
    (
        'llm',
        'listen_discover_needs_a',
    ): '7dd8cc501e86b091ae432bd57556ba5023d03c1d758cb2b2ec7326d2a2e7acbe',
    (
        'llm',
        'listen_discover_needs_b',
    ): '7dd8cc501e86b091ae432bd57556ba5023d03c1d758cb2b2ec7326d2a2e7acbe',
    (
        'llm',
        'consolidate',
    ): '743b58c48581d4f0300f90d5f958c5e179232d6d02088954751260e80414c3e8',
    (
        'llm',
        'draft_hypothesis_full',
    ): '1d2cfb7867552f3037438c64f44677a514a4e6c589b98138f863d54aade9362c',
    (
        'llm',
        'draft_hypothesis_smoke',
    ): '1d2cfb7867552f3037438c64f44677a514a4e6c589b98138f863d54aade9362c',
    (
        'llm',
        'draft_price',
    ): '326438c2d3728821c228070fa7f80374bea52739d0e742d91dcf9b6b1e75ffbc',
    (
        'llm',
        'edit_serge_md',
    ): '743b58c48581d4f0300f90d5f958c5e179232d6d02088954751260e80414c3e8',
    (
        'llm',
        'extract_meeting',
    ): '4d145872af6cc385b461d8b6896aec40e53103779af3d935519b3d7f7ac270c5',
    (
        'llm',
        'fill_slots',
    ): '25aba9c2543828d3067797a646f19bd436bb453f3f853478a685087a2487a686',
    (
        'llm',
        'install_guide',
    ): '168908aa33b9caec9dfee3b332d8e9d4e3b7088d07ed3341371ee4435ea5995c',
    (
        'llm',
        'judge_allocator',
    ): 'f65a46373bce8f030b1eccec8978cf224e0dacf74d1a315979e43e47a2cc563d',
    (
        'llm',
        'judge_consequence',
    ): '01826b8f4db329628ed1645466d8e44ad8795a671eaa747f59f776c70e907d94',
    (
        'llm',
        'options_pivot',
    ): 'c8b012bef657300aa13789105a04270375d559997a82e053b7af1ef574a7f524',
    (
        'llm',
        'plan_scale',
    ): 'c8b012bef657300aa13789105a04270375d559997a82e053b7af1ef574a7f524',
    (
        'llm',
        'qualify_prospect',
    ): '08f18aa83856fdbf8f09301f1211168b3993557aa9675d87ef9875e9decc91dc',
    (
        'llm',
        'render_context_fr',
    ): '01826b8f4db329628ed1645466d8e44ad8795a671eaa747f59f776c70e907d94',
    (
        'llm',
        'reply_intent',
    ): '52dd06efafcb0f09080c1ceba2de6efadbfc3afae0b3e9623da2d0767fa09f4b',
    (
        'llm',
        'resume_test',
    ): 'c8b012bef657300aa13789105a04270375d559997a82e053b7af1ef574a7f524',
    (
        'llm',
        'review_build',
    ): '9ce5456009b3e3e9a3f831f4f18a69cfc729440c0f90558d0d1c83b845ab716e',
    (
        'llm',
        'review_other',
    ): 'b8d34984be168d02e6132538efed1437d37805a7624f4bd11801b3c6344646a9',
    (
        'llm',
        'score_call',
    ): 'bf1b2e3f68ef6703e3fb8e97b394f81f93e2a0640357b775f1ed424453fc644d',
    (
        'llm',
        'score_lead_departage',
    ): '08f18aa83856fdbf8f09301f1211168b3993557aa9675d87ef9875e9decc91dc',
    (
        'llm',
        'summarize_build_debt',
    ): '9ce5456009b3e3e9a3f831f4f18a69cfc729440c0f90558d0d1c83b845ab716e',
    (
        'llm',
        'summarize_thread',
    ): 'bf1b2e3f68ef6703e3fb8e97b394f81f93e2a0640357b775f1ed424453fc644d',
    (
        'llm',
        'voice_dialog',
    ): 'e310ddfc003fdf81436fe63596db122ec49af3a264c290b4f8292fec993b5daa',
    (
        'llm',
        'voice_script',
    ): '0c2a2837c7b504f3977ce3e9acc6a05688b54218a569e41bf687c4cfbad047dc',
    (
        'llm',
        'write_followup',
    ): '25aba9c2543828d3067797a646f19bd436bb453f3f853478a685087a2487a686',
    (
        'outil',
        'agenda',
    ): 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    (
        'outil',
        'boite_serge',
    ): 'bd23fbd3b6e0f612a913404e37b7def202b8a09fdda3cf21a25c325dfc10c6b7',
    (
        'outil',
        'catalogue',
    ): 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    (
        'outil',
        'demande_capacite',
    ): 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    (
        'outil',
        'fiches',
    ): 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    (
        'outil',
        'identity_advanced',
    ): '5d695c4535a4dde940832f596d24fb5cf0f668850132efc42dd574e0212bef1b',
    (
        'outil',
        'identity_basique',
    ): '5d695c4535a4dde940832f596d24fb5cf0f668850132efc42dd574e0212bef1b',
    (
        'outil',
        'memory_search',
    ): 'c28e81cd9475e25fcd2daaf0a0951ab7b456de38e9e8269138a1c26d090df730',
    (
        'outil',
        'db_read',
    ): '75cdfcbbb7c26dd380839db5cd95d652a96740d4d7dab4446da21242d0172fa2',
    (
        'outil',
        'navigateur',
    ): 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    (
        'outil',
        'web_search',
    ): '831a2747280388ad9dfa275930fdbd30b09e57f31c2667380cd12768129cbeed',
    (
        'tech',
        'cluster_listen',
    ): '99b2b8c8a2d6ceed88bc54a1503d27f4c71034dc7d55f9fa61d5e83b121a5796',
    (
        'tech',
        'dunning',
    ): '4ea7b789a55ec926c14423a65cbe9305e9a2d4be500a7664d5a6f9ac8fe6cf74',
    (
        'tech',
        'guards_check',
    ): 'fc1d5a258cb349af3ac3cbdb65ca33971efdf29c6aabf665793a3b81da0654bf',
    (
        'tech',
        'listen_collect',
    ): 'c21b86c84da79cfe07c4c741e01373e80dc4afabf45825e23e2e025265648687',
    (
        'tech',
        'memory_fts_index',
    ): 'c28e81cd9475e25fcd2daaf0a0951ab7b456de38e9e8269138a1c26d090df730',
    (
        'tech',
        'metrics_u',
    ): 'eaea16e8748b7f837629da53a86ca8d6bf51df59dd761bf42cf4f74a40060ba6',
    (
        'tech',
        'select_pre_venture',
    ): 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    (
        'tech',
        'sequencer',
    ): '9eb5732066a8df38fb130be9a57cc4670696298061e650bc2f042fe328247cae',
    (
        'tech',
        'stripe_receive',
    ): '8d832135d052475f4b24de6c22e1678be8ae8e7786cdd1c19a2811a4b85e586f',
}
