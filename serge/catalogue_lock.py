#!/usr/bin/env python3
"""SHA figés du catalogue (fichiers + sous-objets). Maj = test rouge sinon."""

from __future__ import annotations

# (kind, id) → files_sha. Contenu des fichiers seulement, puis compose.
SHA_ATTENDUS: dict[tuple[str, str], str] = {
    (
        'canal',
        'email',
    ): 'cc299f003e5378af05e0626fd03aa72709a2e91b1349c90671d382a613b21be1',
    (
        'canal',
        'voice',
    ): 'b798f17fcd66e9291cd3013ecf83ca8561b979bf834284cb775ffb017f2ae2fc',
    (
        'etape',
        'build_venture',
    ): '248110a8728ca027ad94fa2eadac70f7a3940f6dd8477d72d49b4864a1d1f0fc',
    (
        'etape',
        'caisse',
    ): '52c4c17ca9b5cded964ddd82d6340eb956fe4e7c356203cc83d2d60ee3732fa0',
    (
        'etape',
        'choix_venture',
    ): '315d5a756cd9fff9224f42386f1bf55396dc75ca2ac3e56de3fbf183e73a1598',
    (
        'etape',
        'collect_feedback',
    ): '7312de062bfcdf3f955eb2b646cf8819c56f0a85d451c5751dfb5d1f3c28e93c',
    (
        'etape',
        'conception_poc',
    ): '9cc03685cc205d6da25635fe77aeaad221a1d3ea83f3cacfa9aaf316e18f6e38',
    (
        'etape',
        'pre_prospection',
    ): '0f79d7f9e6c91f4e7a24b71e1c11ad6f2982f20fff2dad6ee4c4358943f7040c',
    (
        'etape',
        'prospection_light',
    ): '351de1af9e87038ca5301cb2611d99e4d5ec5e4329293e47de14e00603420efa',
    (
        'etape',
        'prospection_lourde',
    ): 'a91c04e7ab760e07f5d4ad4f499074f1e5b0fbf206b66c3dcceb9d7997b88a74',
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
    ): 'fc058dfa58a70e9e442dc6d82533a29f3f10e08694ce104f304bf10e713663c8',
    (
        'llm',
        'classify_owner_intent',
    ): 'fa2b6ac77b212a777403ff3dddf9a1ff1f7922c43e895bf1df844690d0cde792',
    (
        'llm',
        'classify_reply',
    ): '598b1f7dcc495e93d2cb938b541888f032325ac0d4f7270f72124f1ee25eae58',
    (
        'llm',
        'cluster_demand',
    ): '57060eccbfc0462a6ac380f4ef263c8ee1079f537e5b103ae12e5a6c0180bf47',
    (
        'llm',
        'listen_choose_poc',
    ): '5765923cc2a447592a7a23393fd71097af8daa07e1c03236a9e2217f4e747d3e',
    (
        'llm',
        'listen_discover_needs_a',
    ): '887d1f2a32ccdaa10bf9c148f4898d5128919921c0af4fca2929820daf70a4bb',
    (
        'llm',
        'listen_discover_needs_b',
    ): '887d1f2a32ccdaa10bf9c148f4898d5128919921c0af4fca2929820daf70a4bb',
    (
        'llm',
        'consolidate',
    ): 'f807b2f184c2fe809da6f0caee13ce0647e7251e231e1dde1dd5b4c260470f29',
    (
        'llm',
        'draft_hypothesis_full',
    ): 'a7c53a58e651692aa370232eafa01a2f247fc7ac0932406114d7d01283ab2e9b',
    (
        'llm',
        'draft_hypothesis_smoke',
    ): 'a7c53a58e651692aa370232eafa01a2f247fc7ac0932406114d7d01283ab2e9b',
    (
        'llm',
        'draft_price',
    ): '1120e298fcabdd526f5ac2191fcd535627d025c853d892494ad7b4fde01dda5b',
    (
        'llm',
        'discover_contacts',
    ): '1a2560dd0352ccc9b975ce1b371f1d9d96d2e59439fff925425539b66900b7ec',
    (
        'llm',
        'edit_serge_md',
    ): 'b0df0688f2b3b5ebcafc203d7d6815dcbaceb7e32b26eef4cb51f4b45eeee076',
    (
        'llm',
        'extract_meeting',
    ): '63411f89d6ce723968ebdc0a1a29b415aeb8ffbace40079e59be7a234518d734',
    (
        'llm',
        'fill_slots',
    ): 'c67db40fe99f00ccf5df23c92a1555908c5f17bcfb5c145bec5f3c6b1858b5db',
    (
        'llm',
        'install_guide',
    ): '555f939a7b6daad3f1644b26fa944348b1a18071e1c77e99fb1294a4a21b94ed',
    (
        'llm',
        'judge_allocator',
    ): 'f3e639916586d56aac99fffb19eb6985d2c345e08b3b8568efd757807559426f',
    (
        'llm',
        'judge_consequence',
    ): '9e53bebe14191bd8dc75b7efd056e409e5236f115a723a89eceb31630b356e0a',
    (
        'llm',
        'options_pivot',
    ): '6c3f626cb897fb110a86901149af463db6a6ef589a13ecabdb8d7aed853201e4',
    (
        'llm',
        'plan_scale',
    ): '6c3f626cb897fb110a86901149af463db6a6ef589a13ecabdb8d7aed853201e4',
    (
        'llm',
        'qualify_prospect',
    ): '42ab716642ec606f2fe665dbabced7cefd13843cbb2b77b7e29b23b1abd6f799',
    (
        'llm',
        'render_context_fr',
    ): 'fa2b6ac77b212a777403ff3dddf9a1ff1f7922c43e895bf1df844690d0cde792',
    (
        'llm',
        'reply_intent',
    ): 'cfe3deef87cb81e94b9ffd0fac2c36a290b353ab804ce439545a71c5b7c348c9',
    (
        'llm',
        'resume_test',
    ): '95098755018ca9b580cbc5b12a27f60db9372c7d6b186d98a285a9e62a55e7aa',
    (
        'llm',
        'review_build',
    ): 'b2c007272e083966aea20d2c51e034b9bf15ccd06beb0d09850847460dd288dd',
    (
        'llm',
        'review_other',
    ): '1648c47052857b426b362dc9e65c800e1149258e2af83e34c8afe7ef7ec53f9b',
    (
        'llm',
        'score_call',
    ): 'cbda7df6d09014fb4ccd784e852e5b80edf5397cefa2c4044d25c54268e71382',
    (
        'llm',
        'score_lead_departage',
    ): '42ab716642ec606f2fe665dbabced7cefd13843cbb2b77b7e29b23b1abd6f799',
    (
        'llm',
        'summarize_build_debt',
    ): 'b2c007272e083966aea20d2c51e034b9bf15ccd06beb0d09850847460dd288dd',
    (
        'llm',
        'summarize_thread',
    ): 'cbda7df6d09014fb4ccd784e852e5b80edf5397cefa2c4044d25c54268e71382',
    (
        'llm',
        'voice_dialog',
    ): 'e1bd181f92fb5f8865bfaac15f34858797b4a687263f6b14681e759964a5f693',
    (
        'llm',
        'voice_script',
    ): 'bfc5d923fa213d5329f45d00420527bfd9204a8411b64bd907520c264e5e9d16',
    (
        'llm',
        'write_followup',
    ): 'c67db40fe99f00ccf5df23c92a1555908c5f17bcfb5c145bec5f3c6b1858b5db',
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
        'contact_upsert',
    ): 'ef0b7d7a13bd5ac5aa1a2d92e1a307de32115cd1db2e0a7c29d95f476c4e280c',
    (
        'outil',
        'catalogue',
    ): 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    (
        'outil',
        'demande_capacite',
    ): '14bc00395e804c0ac6d02c8e0271673df4909b0ba7f2bfef66fd2c8ce723b067',
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
    ): '7d837282c0e1e0c685bfd99ff3d581168adc1696fb5058c24ebe9986a92a798e',
    (
        'outil',
        'current_listen_cycle',
    ): '32168f46aa0d0224f7def70ab30e33e1c132b58ecbd5cede4d73466f8574f455',
    (
        'outil',
        'listen_cycle_documents',
    ): '32168f46aa0d0224f7def70ab30e33e1c132b58ecbd5cede4d73466f8574f455',
    (
        'outil',
        'known_business_candidates',
    ): '32168f46aa0d0224f7def70ab30e33e1c132b58ecbd5cede4d73466f8574f455',
    (
        'outil',
        'eligible_poc_candidates',
    ): '32168f46aa0d0224f7def70ab30e33e1c132b58ecbd5cede4d73466f8574f455',
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
    ): '7d837282c0e1e0c685bfd99ff3d581168adc1696fb5058c24ebe9986a92a798e',
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
        'stripe_receive',
    ): '8d832135d052475f4b24de6c22e1678be8ae8e7786cdd1c19a2811a4b85e586f',
}
