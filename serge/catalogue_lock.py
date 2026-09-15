#!/usr/bin/env python3
"""SHA figés du catalogue (fichiers + sous-objets). Maj = test rouge sinon."""

from __future__ import annotations

# (kind, id) → files_sha. Contenu des fichiers seulement, puis compose.
SHA_ATTENDUS: dict[tuple[str, str], str] = {
    (
        'etape',
        'build_venture',
    ): '7485b369989ee1cea7c64a3db0daebbbbf2dcd9a889abd5985e31665b69d4a8f',
    (
        'etape',
        'caisse',
    ): '0adf27ead5e61abe5d425b91e36a8c8ecb9c0680189f0d26a1db43070572a698',
    (
        'etape',
        'choix_venture',
    ): '93046e2189a9faefc65bf343152584239659cafdf1a3a5279243ee2d7ebe5eae',
    (
        'etape',
        'collect_feedback',
    ): '8cdd27c226c95af8ac29349cd19903ae0628e67e02ccdb45f635acd05bce95f7',
    (
        'etape',
        'conception_poc',
    ): 'cde75bc00e04b8e4f5c716d76e6b4a6676f99a7e7dbe953d65304c95ab8efb94',
    (
        'etape',
        'pre_prospection',
    ): '95a0f5c6486249dbf0d918c4dccaa11dbc395bf2f414274982566527fd6b0747',
    (
        'etape',
        'prospection_light',
    ): 'e69809f2240d32143be375b9f05479dbbcf611c3cdc2b287d8bc59b6c70b55fc',
    (
        'etape',
        'prospection_lourde',
    ): 'ac296d09e87c2fdc68745c5a0ac6ed7baa58188c4f9f98d2095e51fea549cc60',
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
    ): '06b12303a5bcdf39b2aabe01f36066a0f738a689746b49236c20e0f9f3168847',
    (
        'llm',
        'classify_owner_intent',
    ): '6671565f7c6faab94f9bbcfdc96a9541975bdb4dacc20c63e5dedf9cc6cdf057',
    (
        'llm',
        'classify_reply',
    ): '9dcfc80b3ef6efd671cd72504b148ed8c95b1394f45a00e26adf2cb025c02067',
    (
        'llm',
        'cluster_demand',
    ): '6cbbad19faff65a7ec5793791ab78fb74bc83b4e1774546677a8c8596100e3c7',
    (
        'llm',
        'consolidate',
    ): '6b9fb715ea6e665fab4f72d64053746f1e245605b43efdea1063ee72f035c669',
    (
        'llm',
        'draft_hypothesis_full',
    ): '44ad4e54a21be02bb86ddb3e40fe40dc28e01ac8ecf36f3d452d42fd4fc317ed',
    (
        'llm',
        'draft_hypothesis_smoke',
    ): '44ad4e54a21be02bb86ddb3e40fe40dc28e01ac8ecf36f3d452d42fd4fc317ed',
    (
        'llm',
        'draft_price',
    ): '5fd4e9b1523d5f93240353af8234cc52fbf6a28af66b0f4263900b93f7a6bdbe',
    (
        'llm',
        'edit_serge_md',
    ): '6b9fb715ea6e665fab4f72d64053746f1e245605b43efdea1063ee72f035c669',
    (
        'llm',
        'extract_meeting',
    ): 'd5c2d63e5ca06c053e0127a6ecedf19a8f00f52202d103a1945c017709dc581f',
    (
        'llm',
        'fill_slots',
    ): '0dbf189418fed6c9ee2e1e66321c1dcc3626d9a38a95f560539fbabf277e309c',
    (
        'llm',
        'install_guide',
    ): 'b861b82c0ebfe591ff2591bc751d3bc9dc7b8016346e0f7e4c5f86c320321c48',
    (
        'llm',
        'judge_allocator',
    ): '473ef50fdc4736c819eba81c3da3d34a431cd7fd9539b6782ffb9344819d667d',
    (
        'llm',
        'judge_consequence',
    ): '6671565f7c6faab94f9bbcfdc96a9541975bdb4dacc20c63e5dedf9cc6cdf057',
    (
        'llm',
        'options_pivot',
    ): '213e21b01bec63946ef3d059d5f1c836ecfa9ff4896044f8804390ece1a43dd8',
    (
        'llm',
        'plan_scale',
    ): '213e21b01bec63946ef3d059d5f1c836ecfa9ff4896044f8804390ece1a43dd8',
    (
        'llm',
        'qualify_prospect',
    ): '6fbc5fee284797e653c286f74ad6a18b43afcb14f06047debc29a7097e7444be',
    (
        'llm',
        'render_context_fr',
    ): '6671565f7c6faab94f9bbcfdc96a9541975bdb4dacc20c63e5dedf9cc6cdf057',
    (
        'llm',
        'reply_intent',
    ): 'd4d06d580ba7b78b88105558887b3bbb39cbcc69c863fcee3dfa1b2fbeb3fc07',
    (
        'llm',
        'resume_test',
    ): '213e21b01bec63946ef3d059d5f1c836ecfa9ff4896044f8804390ece1a43dd8',
    (
        'llm',
        'review_build',
    ): '151bd7c67609003c91695cca938f589fd9e557ac4711c736e850e205beaa1012',
    (
        'llm',
        'review_other',
    ): '0e13ebc7f168bb287671d18342057ecdbf02e094d332af001e6b545cb3d94225',
    (
        'llm',
        'score_call',
    ): '84415a403b76f3e917fc802c34c7e8640824ae2c5487b6cac499f566bd201a6f',
    (
        'llm',
        'score_lead_departage',
    ): '6fbc5fee284797e653c286f74ad6a18b43afcb14f06047debc29a7097e7444be',
    (
        'llm',
        'summarize_build_debt',
    ): '151bd7c67609003c91695cca938f589fd9e557ac4711c736e850e205beaa1012',
    (
        'llm',
        'summarize_thread',
    ): '84415a403b76f3e917fc802c34c7e8640824ae2c5487b6cac499f566bd201a6f',
    (
        'llm',
        'voice_dialog',
    ): '4456c481ce1d99f1ac437a23059fd6d455af9397b178b97507275aa586639827',
    (
        'llm',
        'voice_script',
    ): '5ed9d48eb1d77b00e53dbd4193167e414ff82ae963bf3faede0036eb9fa8f358',
    (
        'llm',
        'write_followup',
    ): '0dbf189418fed6c9ee2e1e66321c1dcc3626d9a38a95f560539fbabf277e309c',
    (
        'canal',
        'email',
    ): 'cc757e2fd186880b8c39b6c84e8819a62e79ac257c87dabdfa687a95965b291f',
    (
        'canal',
        'voice',
    ): 'cdfc6e7351890d553232d2b571d503b5cab4d7c4929076c94448556a66e2f367',
    (
        'outil',
        'agenda',
    ): 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
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
        'memory_search',
    ): 'c28e81cd9475e25fcd2daaf0a0951ab7b456de38e9e8269138a1c26d090df730',
    (
        'outil',
        'navigateur',
    ): 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
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
    ): '48452441ca9632a17990c937a68918d787cda64bbbfd85f4747e77e1fb477b04',
    (
        'tech',
        'stripe_receive',
    ): '8d832135d052475f4b24de6c22e1678be8ae8e7786cdd1c19a2811a4b85e586f',
}
