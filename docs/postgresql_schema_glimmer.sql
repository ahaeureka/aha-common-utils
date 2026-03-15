-- 照见一念（Glimmer）PostgreSQL 建表语句
-- 基于当前 UI/UX 原型、PRD 与后端接口设计整理
-- 日期：2026-03-11
-- 说明：本文件为 PostgreSQL 15+ 推荐写法，所有字段均附带注释

BEGIN;

-- =========================================================
-- 0. 通用说明
-- =========================================================
-- 约定：
-- 1. 业务主键统一使用 varchar(64)，便于兼容前端生成或服务端雪花/短 UUID 策略。
-- 2. 时间统一使用 timestamptz。
-- 3. 结构化扩展字段统一使用 jsonb。
-- 4. 本文件不强依赖 users 表；如有用户体系，可将 user_id 外键补齐。

-- =========================================================
-- 1. sessions
-- =========================================================
CREATE TABLE IF NOT EXISTS sessions (
    id varchar(64) PRIMARY KEY,
    user_id varchar(64) NULL,
    status varchar(32) NOT NULL,
    question_text text NOT NULL,
    question_normalized_text text NULL,
    question_category varchar(32) NOT NULL,
    question_source varchar(32) NOT NULL DEFAULT 'manual_input',
    soothing_entry_source varchar(32) NULL,
    soothing_program varchar(32) NULL,
    soothing_duration_seconds integer NULL,
    soothing_completed boolean NOT NULL DEFAULT false,
    emotion_tag varchar(32) NULL,
    emotion_after_tag varchar(32) NULL,
    emotion_label varchar(64) NULL,
    emotion_source varchar(32) NULL,
    emotion_confidence numeric(5,4) NULL,
    insight_mode varchar(32) NULL,
    mode_source varchar(32) NULL,
    journal_note text NULL,
    followup_note text NULL,
    followup_at timestamptz NULL,
    selected_card_id varchar(64) NULL,
    risk_level varchar(16) NULL,
    is_saved boolean NOT NULL DEFAULT false,
    completed_at timestamptz NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_sessions_status CHECK (
        status IN (
            'draft',
            'soothing',
            'unload_capturing',
            'question_refined',
            'context_ready',
            'answer_generating',
            'answer_ready',
            'reflection_in_progress',
            'summary_generating',
            'completed',
            'saved',
            'risk_blocked',
            'failed',
            'archived'
        )
    ),
    CONSTRAINT chk_sessions_question_category CHECK (
        question_category IN ('career', 'relationship', 'life', 'emotion', 'self_growth', 'other')
    ),
    CONSTRAINT chk_sessions_question_source CHECK (
        question_source IN ('manual_input', 'example_chip', 'history_retry', 'freeform_unload', 'voice_transcript')
    ),
    CONSTRAINT chk_sessions_soothing_program CHECK (
        soothing_program IS NULL OR soothing_program IN ('breathing', 'grounding', 'pause')
    ),
    CONSTRAINT chk_sessions_emotion_source CHECK (
        emotion_source IS NULL OR emotion_source IN ('user_selected', 'model_inferred')
    ),
    CONSTRAINT chk_sessions_mode CHECK (
        insight_mode IS NULL OR insight_mode IN ('reflective', 'decisive')
    ),
    CONSTRAINT chk_sessions_mode_source CHECK (
        mode_source IS NULL OR mode_source IN ('user_selected', 'system_recommended', 'defaulted')
    ),
    CONSTRAINT chk_sessions_risk_level CHECK (
        risk_level IS NULL OR risk_level IN ('low', 'medium', 'high', 'critical')
    ),
    CONSTRAINT chk_sessions_emotion_confidence CHECK (
        emotion_confidence IS NULL OR (emotion_confidence >= 0 AND emotion_confidence <= 1)
    )
);

COMMENT ON TABLE sessions IS '单次照见会话主表，承载问题、上下文、状态与汇总索引字段。';
COMMENT ON COLUMN sessions.id IS '会话主键，建议使用 sess_ 前缀业务 ID。';
COMMENT ON COLUMN sessions.user_id IS '用户 ID，可为空，兼容未登录或匿名模式。';
COMMENT ON COLUMN sessions.status IS '会话状态机状态，例如 draft、answer_ready、completed。';
COMMENT ON COLUMN sessions.question_text IS '用户原始输入的问题文本。';
COMMENT ON COLUMN sessions.question_normalized_text IS '清洗、脱敏、归一化后的问题文本。';
COMMENT ON COLUMN sessions.question_category IS '问题分类，如职业、关系、生活、情绪、自我成长、其他。';
COMMENT ON COLUMN sessions.question_source IS '问题来源，手输、示例点击或历史重问。';
COMMENT ON COLUMN sessions.soothing_entry_source IS '稳定入口来源，如 home_cta、result_pause、history_resume。';
COMMENT ON COLUMN sessions.soothing_program IS '稳定方式，如 breathing、grounding、pause。';
COMMENT ON COLUMN sessions.soothing_duration_seconds IS '稳定步骤时长，单位秒。';
COMMENT ON COLUMN sessions.soothing_completed IS '是否完成一次稳定步骤。';
COMMENT ON COLUMN sessions.emotion_tag IS '情绪标签编码，如 anxious、tired、unclear。';
COMMENT ON COLUMN sessions.emotion_after_tag IS '反思或总结结束后的情绪标签。';
COMMENT ON COLUMN sessions.emotion_label IS '情绪标签中文展示文案。';
COMMENT ON COLUMN sessions.emotion_source IS '情绪来源，用户主动选择或模型推断。';
COMMENT ON COLUMN sessions.emotion_confidence IS '模型推断情绪时的置信度，范围 0 到 1。';
COMMENT ON COLUMN sessions.insight_mode IS '照见模式编码，reflective 或 decisive。';
COMMENT ON COLUMN sessions.mode_source IS '模式来源，用户选择、系统推荐或默认值。';
COMMENT ON COLUMN sessions.journal_note IS '用户保存的一句话情绪日记。';
COMMENT ON COLUMN sessions.followup_note IS '用户后续回访补记。';
COMMENT ON COLUMN sessions.followup_at IS '回访补记写入时间。';
COMMENT ON COLUMN sessions.selected_card_id IS '用户最终选中的反思卡业务 ID。';
COMMENT ON COLUMN sessions.risk_level IS '会话当前命中的最高风险等级。';
COMMENT ON COLUMN sessions.is_saved IS '用户是否主动保存了本次会话。';
COMMENT ON COLUMN sessions.completed_at IS '会话完成总结与行动建议的时间。';
COMMENT ON COLUMN sessions.created_at IS '会话创建时间。';
COMMENT ON COLUMN sessions.updated_at IS '会话更新时间。';

CREATE INDEX IF NOT EXISTS idx_sessions_user_created_at ON sessions (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions (status);
CREATE INDEX IF NOT EXISTS idx_sessions_question_category ON sessions (question_category);
CREATE INDEX IF NOT EXISTS idx_sessions_emotion_tag ON sessions (emotion_tag);
CREATE INDEX IF NOT EXISTS idx_sessions_insight_mode ON sessions (insight_mode);
CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_followup_at ON sessions (followup_at DESC);

-- =========================================================
-- 2. session_answers
-- =========================================================
CREATE TABLE IF NOT EXISTS session_answers (
    id varchar(64) PRIMARY KEY,
    session_id varchar(64) NOT NULL,
    answer_type varchar(32) NOT NULL,
    answer_text text NOT NULL,
    hint_text text NOT NULL,
    display_tags jsonb NOT NULL DEFAULT '[]'::jsonb,
    model_provider varchar(64) NOT NULL,
    model_name varchar(128) NOT NULL,
    template_version varchar(32) NOT NULL,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_session_answers_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    CONSTRAINT chk_session_answers_type CHECK (
        answer_type IN ('action_probe', 'delay', 'observe', 'emotion_check', 'value_check', 'time_perspective', 'risk_check')
    )
);

COMMENT ON TABLE session_answers IS '启发式答案结果表，存储结果页主回答与提示。';
COMMENT ON COLUMN session_answers.id IS '答案记录主键，建议使用 ans_ 前缀业务 ID。';
COMMENT ON COLUMN session_answers.session_id IS '所属会话 ID。';
COMMENT ON COLUMN session_answers.answer_type IS '答案策略类型，如 action_probe、delay、observe。';
COMMENT ON COLUMN session_answers.answer_text IS '结果页主启发语。';
COMMENT ON COLUMN session_answers.hint_text IS '主启发语下方的解释性提示文案。';
COMMENT ON COLUMN session_answers.display_tags IS '结果页可展示的轻量标签列表，jsonb 数组格式。';
COMMENT ON COLUMN session_answers.model_provider IS '生成该答案的模型服务提供方。';
COMMENT ON COLUMN session_answers.model_name IS '生成该答案的模型名称。';
COMMENT ON COLUMN session_answers.template_version IS '答案生成所使用的 Prompt 或模板版本。';
COMMENT ON COLUMN session_answers.raw_payload IS '模型原始结构化返回，便于追溯与调试。';
COMMENT ON COLUMN session_answers.created_at IS '答案生成时间。';

CREATE INDEX IF NOT EXISTS idx_session_answers_session_id ON session_answers (session_id);
CREATE INDEX IF NOT EXISTS idx_session_answers_answer_type ON session_answers (answer_type);

-- =========================================================
-- 2A. session_unload_drafts
-- =========================================================
CREATE TABLE IF NOT EXISTS session_unload_drafts (
    id varchar(64) PRIMARY KEY,
    session_id varchar(64) NOT NULL,
    source varchar(32) NOT NULL,
    raw_text text NOT NULL,
    raw_text_length integer NOT NULL,
    refined_question_text text NULL,
    focus_options jsonb NOT NULL DEFAULT '[]'::jsonb,
    user_confirmed_question_text text NULL,
    selected_focus text NULL,
    decide_later boolean NOT NULL DEFAULT false,
    refinement_confidence numeric(5,4) NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    refined_at timestamptz NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_session_unload_drafts_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    CONSTRAINT uq_session_unload_drafts_session UNIQUE (session_id),
    CONSTRAINT chk_session_unload_drafts_source CHECK (
        source IN ('free_text', 'voice_transcript')
    ),
    CONSTRAINT chk_session_unload_drafts_refinement_confidence CHECK (
        refinement_confidence IS NULL OR (refinement_confidence >= 0 AND refinement_confidence <= 1)
    )
);

COMMENT ON TABLE session_unload_drafts IS '自由倾诉承接表，保存原始表达与整理后的标准问题。';
COMMENT ON COLUMN session_unload_drafts.id IS '自由倾诉草稿主键，建议使用 unload_ 前缀业务 ID。';
COMMENT ON COLUMN session_unload_drafts.session_id IS '所属会话 ID。';
COMMENT ON COLUMN session_unload_drafts.source IS '倾诉来源，文本输入或语音转写。';
COMMENT ON COLUMN session_unload_drafts.raw_text IS '用户原始自由倾诉内容。';
COMMENT ON COLUMN session_unload_drafts.raw_text_length IS '原文长度。';
COMMENT ON COLUMN session_unload_drafts.refined_question_text IS '整理后的主问题文本。';
COMMENT ON COLUMN session_unload_drafts.focus_options IS '问题整理后推荐给用户选择的 1–2 个继续侧重点。';
COMMENT ON COLUMN session_unload_drafts.user_confirmed_question_text IS '用户最终确认或改写后的主问题文本。';
COMMENT ON COLUMN session_unload_drafts.selected_focus IS '用户最终选中的继续侧重点。';
COMMENT ON COLUMN session_unload_drafts.decide_later IS '用户是否在问题整理页选择了先不决定。';
COMMENT ON COLUMN session_unload_drafts.refinement_confidence IS '问题整理置信度。';
COMMENT ON COLUMN session_unload_drafts.created_at IS '创建时间。';
COMMENT ON COLUMN session_unload_drafts.refined_at IS '问题完成提炼的时间。';
COMMENT ON COLUMN session_unload_drafts.updated_at IS '更新时间。';

CREATE INDEX IF NOT EXISTS idx_session_unload_drafts_session_id ON session_unload_drafts (session_id);
CREATE INDEX IF NOT EXISTS idx_session_unload_drafts_source ON session_unload_drafts (source);
CREATE INDEX IF NOT EXISTS idx_session_unload_drafts_decide_later ON session_unload_drafts (decide_later);

-- =========================================================
-- 2B. session_resume_snapshots
-- =========================================================
CREATE TABLE IF NOT EXISTS session_resume_snapshots (
    id varchar(64) PRIMARY KEY,
    session_id varchar(64) NOT NULL,
    resumable_step varchar(32) NOT NULL,
    question_preview text NULL,
    last_emotion_tag varchar(32) NULL,
    available_actions jsonb NOT NULL DEFAULT '[]'::jsonb,
    priority_score numeric(6,4) NOT NULL DEFAULT 0,
    resume_count integer NOT NULL DEFAULT 0,
    dismissed_at timestamptz NULL,
    expires_at timestamptz NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_session_resume_snapshots_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    CONSTRAINT uq_session_resume_snapshots_session UNIQUE (session_id),
    CONSTRAINT chk_session_resume_snapshots_step CHECK (
        resumable_step IN ('unload', 'question_refined', 'answer_ready', 'reflection_in_progress', 'completed')
    ),
    CONSTRAINT chk_session_resume_snapshots_priority CHECK (
        priority_score >= 0 AND priority_score <= 1
    ),
    CONSTRAINT chk_session_resume_snapshots_resume_count CHECK (
        resume_count >= 0
    )
);

COMMENT ON TABLE session_resume_snapshots IS '未完成会话恢复快照表，用于首页和历史页恢复入口。';
COMMENT ON COLUMN session_resume_snapshots.id IS '恢复快照主键，建议使用 resume_ 前缀业务 ID。';
COMMENT ON COLUMN session_resume_snapshots.session_id IS '所属会话 ID。';
COMMENT ON COLUMN session_resume_snapshots.resumable_step IS '当前最适合恢复的步骤。';
COMMENT ON COLUMN session_resume_snapshots.question_preview IS '恢复浮层展示的问题摘要。';
COMMENT ON COLUMN session_resume_snapshots.last_emotion_tag IS '最近一次有效情绪标签。';
COMMENT ON COLUMN session_resume_snapshots.available_actions IS '前端允许展示的恢复动作列表。';
COMMENT ON COLUMN session_resume_snapshots.priority_score IS '恢复优先级分值，范围 0 到 1。';
COMMENT ON COLUMN session_resume_snapshots.resume_count IS '该会话被恢复尝试的次数。';
COMMENT ON COLUMN session_resume_snapshots.dismissed_at IS '用户显式忽略本次恢复入口的时间。';
COMMENT ON COLUMN session_resume_snapshots.expires_at IS '恢复入口失效时间。';
COMMENT ON COLUMN session_resume_snapshots.updated_at IS '更新时间。';
COMMENT ON COLUMN session_resume_snapshots.created_at IS '创建时间。';

CREATE INDEX IF NOT EXISTS idx_session_resume_snapshots_step ON session_resume_snapshots (resumable_step);
CREATE INDEX IF NOT EXISTS idx_session_resume_snapshots_priority ON session_resume_snapshots (priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_session_resume_snapshots_expires_at ON session_resume_snapshots (expires_at);

-- =========================================================
-- 3. session_cards
-- =========================================================
CREATE TABLE IF NOT EXISTS session_cards (
    id bigserial PRIMARY KEY,
    session_id varchar(64) NOT NULL,
    card_id varchar(64) NOT NULL,
    card_type varchar(64) NOT NULL,
    title varchar(255) NOT NULL,
    description text NOT NULL,
    question_text text NOT NULL,
    psychological_dimension varchar(32) NOT NULL,
    is_reverse_check boolean NOT NULL DEFAULT false,
    display_order integer NOT NULL,
    is_selected boolean NOT NULL DEFAULT false,
    selected_at timestamptz NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_session_cards_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    CONSTRAINT uq_session_cards_session_card UNIQUE (session_id, card_id),
    CONSTRAINT chk_session_cards_dimension CHECK (
        psychological_dimension IN ('emotion', 'motivation', 'risk', 'value', 'time', 'relationship')
    )
);

COMMENT ON TABLE session_cards IS '反思卡片表，对应思考卡片页的 3 张或更多结构化卡片。';
COMMENT ON COLUMN session_cards.id IS '自增主键。';
COMMENT ON COLUMN session_cards.session_id IS '所属会话 ID。';
COMMENT ON COLUMN session_cards.card_id IS '业务卡片 ID，前端交互与接口传参使用。';
COMMENT ON COLUMN session_cards.card_type IS '卡片类型编码，如 value_check、future_self、reverse_check。';
COMMENT ON COLUMN session_cards.title IS '卡片标题。';
COMMENT ON COLUMN session_cards.description IS '卡片解释文案。';
COMMENT ON COLUMN session_cards.question_text IS '卡片引导问题正文。';
COMMENT ON COLUMN session_cards.psychological_dimension IS '心理维度，如情绪、动机、风险、价值、时间、关系。';
COMMENT ON COLUMN session_cards.is_reverse_check IS '是否为反向验证卡。';
COMMENT ON COLUMN session_cards.display_order IS '卡片展示顺序。';
COMMENT ON COLUMN session_cards.is_selected IS '该卡片是否被用户选中。';
COMMENT ON COLUMN session_cards.selected_at IS '用户选择该卡片的时间。';
COMMENT ON COLUMN session_cards.created_at IS '卡片生成时间。';

CREATE INDEX IF NOT EXISTS idx_session_cards_session_id ON session_cards (session_id);
CREATE INDEX IF NOT EXISTS idx_session_cards_dimension ON session_cards (psychological_dimension);
CREATE INDEX IF NOT EXISTS idx_session_cards_selected ON session_cards (is_selected);

-- =========================================================
-- 4. session_reflection_turns
-- =========================================================
CREATE TABLE IF NOT EXISTS session_reflection_turns (
    id varchar(64) PRIMARY KEY,
    session_id varchar(64) NOT NULL,
    role varchar(16) NOT NULL,
    turn_type varchar(32) NOT NULL,
    text text NOT NULL,
    sequence_no integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_session_reflection_turns_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    CONSTRAINT uq_session_reflection_turns_sequence UNIQUE (session_id, sequence_no),
    CONSTRAINT chk_session_reflection_turns_role CHECK (
        role IN ('assistant', 'user', 'system')
    ),
    CONSTRAINT chk_session_reflection_turns_type CHECK (
        turn_type IN ('prompt', 'reply', 'followup', 'summary_transition')
    )
);

COMMENT ON TABLE session_reflection_turns IS '深度反思轮次表，兼容单次回答与多轮引导式反思。';
COMMENT ON COLUMN session_reflection_turns.id IS '反思轮次主键，建议使用 turn_ 前缀业务 ID。';
COMMENT ON COLUMN session_reflection_turns.session_id IS '所属会话 ID。';
COMMENT ON COLUMN session_reflection_turns.role IS '消息角色，assistant、user 或 system。';
COMMENT ON COLUMN session_reflection_turns.turn_type IS '轮次类型，如 prompt、reply、followup、summary_transition。';
COMMENT ON COLUMN session_reflection_turns.text IS '该轮次的消息文本。';
COMMENT ON COLUMN session_reflection_turns.sequence_no IS '该轮次在会话中的顺序号。';
COMMENT ON COLUMN session_reflection_turns.created_at IS '该轮次生成或提交时间。';

CREATE INDEX IF NOT EXISTS idx_session_reflection_turns_session_id ON session_reflection_turns (session_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_session_reflection_turns_role ON session_reflection_turns (role);

-- =========================================================
-- 5. session_summaries
-- =========================================================
CREATE TABLE IF NOT EXISTS session_summaries (
    id varchar(64) PRIMARY KEY,
    session_id varchar(64) NOT NULL,
    summary_text text NOT NULL,
    key_insight text NULL,
    future_self_role varchar(64) NULL,
    future_self_message text NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_session_summaries_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    CONSTRAINT uq_session_summaries_session UNIQUE (session_id)
);

COMMENT ON TABLE session_summaries IS '反思总结结果表，包含总结正文与未来自我模块。';
COMMENT ON COLUMN session_summaries.id IS '总结记录主键，建议使用 sum_ 前缀业务 ID。';
COMMENT ON COLUMN session_summaries.session_id IS '所属会话 ID。';
COMMENT ON COLUMN session_summaries.summary_text IS '总结与洞察正文。';
COMMENT ON COLUMN session_summaries.key_insight IS '可选核心洞察摘要，用于高亮展示或分享。';
COMMENT ON COLUMN session_summaries.future_self_role IS '未来自我角色名称，如 一年后的你、三个月后的你。';
COMMENT ON COLUMN session_summaries.future_self_message IS '未来自我模块展示内容。';
COMMENT ON COLUMN session_summaries.created_at IS '总结生成时间。';

CREATE INDEX IF NOT EXISTS idx_session_summaries_session_id ON session_summaries (session_id);

-- =========================================================
-- 6. session_cognitive_biases
-- =========================================================
CREATE TABLE IF NOT EXISTS session_cognitive_biases (
    id varchar(64) PRIMARY KEY,
    session_id varchar(64) NOT NULL,
    bias_code varchar(32) NOT NULL,
    bias_label varchar(64) NOT NULL,
    message text NOT NULL,
    confidence numeric(5,4) NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_session_cognitive_biases_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    CONSTRAINT chk_session_cognitive_biases_code CHECK (
        bias_code IN ('catastrophizing', 'loss_aversion', 'sunk_cost', 'present_bias', 'external_validation', 'confirmation_bias')
    ),
    CONSTRAINT chk_session_cognitive_biases_confidence CHECK (
        confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
    )
);

COMMENT ON TABLE session_cognitive_biases IS '认知偏差提示表，对应总结页中的偏差提醒模块。';
COMMENT ON COLUMN session_cognitive_biases.id IS '认知偏差记录主键。';
COMMENT ON COLUMN session_cognitive_biases.session_id IS '所属会话 ID。';
COMMENT ON COLUMN session_cognitive_biases.bias_code IS '偏差编码，如 catastrophizing、loss_aversion。';
COMMENT ON COLUMN session_cognitive_biases.bias_label IS '偏差中文名称。';
COMMENT ON COLUMN session_cognitive_biases.message IS '偏差提醒文案。';
COMMENT ON COLUMN session_cognitive_biases.confidence IS '偏差识别置信度，范围 0 到 1。';
COMMENT ON COLUMN session_cognitive_biases.created_at IS '偏差记录创建时间。';

CREATE INDEX IF NOT EXISTS idx_session_cognitive_biases_session_id ON session_cognitive_biases (session_id);
CREATE INDEX IF NOT EXISTS idx_session_cognitive_biases_code ON session_cognitive_biases (bias_code);

-- =========================================================
-- 7. session_actions
-- =========================================================
CREATE TABLE IF NOT EXISTS session_actions (
    id varchar(64) PRIMARY KEY,
    session_id varchar(64) NOT NULL,
    action_type varchar(32) NOT NULL,
    action_text text NOT NULL,
    action_reason text NOT NULL,
    if_then_plan text NULL,
    estimated_minutes integer NULL,
    is_reversible boolean NOT NULL DEFAULT true,
    action_status varchar(32) NULL,
    is_adopted boolean NOT NULL DEFAULT false,
    adopted_at timestamptz NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_session_actions_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    CONSTRAINT uq_session_actions_session UNIQUE (session_id),
    CONSTRAINT chk_session_actions_type CHECK (
        action_type IN ('info_collect', 'clarify', 'emotion_stabilize', 'small_probe', 'self_reflection')
    ),
    CONSTRAINT chk_session_actions_status CHECK (
        action_status IS NULL OR action_status IN ('pending', 'adopted', 'not_started', 'paused')
    ),
    CONSTRAINT chk_session_actions_estimated_minutes CHECK (
        estimated_minutes IS NULL OR estimated_minutes >= 0)
);

COMMENT ON TABLE session_actions IS '微实验行动表，对应总结页右侧行动卡。';
COMMENT ON COLUMN session_actions.id IS '行动记录主键，建议使用 act_ 前缀业务 ID。';
COMMENT ON COLUMN session_actions.session_id IS '所属会话 ID。';
COMMENT ON COLUMN session_actions.action_type IS '行动类型，如信息收集、澄清、自我稳定、小范围试探。';
COMMENT ON COLUMN session_actions.action_text IS '建议执行的微实验文本。';
COMMENT ON COLUMN session_actions.action_reason IS '解释为什么推荐这一步。';
COMMENT ON COLUMN session_actions.if_then_plan IS '如果—那么实施意图计划文本。';
COMMENT ON COLUMN session_actions.estimated_minutes IS '预估完成时长，单位分钟。';
COMMENT ON COLUMN session_actions.is_reversible IS '该行动是否可逆。';
COMMENT ON COLUMN session_actions.action_status IS '行动当前状态，如 pending、adopted、not_started、paused。';
COMMENT ON COLUMN session_actions.is_adopted IS '用户是否点击采纳该行动。';
COMMENT ON COLUMN session_actions.adopted_at IS '用户采纳该行动的时间。';
COMMENT ON COLUMN session_actions.created_at IS '行动建议生成时间。';

CREATE INDEX IF NOT EXISTS idx_session_actions_session_id ON session_actions (session_id);
CREATE INDEX IF NOT EXISTS idx_session_actions_type ON session_actions (action_type);
CREATE INDEX IF NOT EXISTS idx_session_actions_adopted ON session_actions (is_adopted);
CREATE INDEX IF NOT EXISTS idx_session_actions_action_status ON session_actions (action_status);

-- =========================================================
-- 8. session_action_tags
-- =========================================================
CREATE TABLE IF NOT EXISTS session_action_tags (
    id bigserial PRIMARY KEY,
    action_id varchar(64) NOT NULL,
    tag_code varchar(32) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_session_action_tags_action FOREIGN KEY (action_id) REFERENCES session_actions(id) ON DELETE CASCADE,
    CONSTRAINT uq_session_action_tags_action_tag UNIQUE (action_id, tag_code),
    CONSTRAINT chk_session_action_tags_code CHECK (
        tag_code IN ('low_risk', 'reversible', 'clarify', 'info_collect', 'emotion_stabilize', 'small_probe')
    )
);

COMMENT ON TABLE session_action_tags IS '微实验行动标签表，对应低风险、可逆、信息收集等标签。';
COMMENT ON COLUMN session_action_tags.id IS '自增主键。';
COMMENT ON COLUMN session_action_tags.action_id IS '所属行动 ID。';
COMMENT ON COLUMN session_action_tags.tag_code IS '行动标签编码。';
COMMENT ON COLUMN session_action_tags.created_at IS '标签创建时间。';

CREATE INDEX IF NOT EXISTS idx_session_action_tags_action_id ON session_action_tags (action_id);
CREATE INDEX IF NOT EXISTS idx_session_action_tags_tag_code ON session_action_tags (tag_code);

-- =========================================================
-- 9. session_risk_events
-- =========================================================
CREATE TABLE IF NOT EXISTS session_risk_events (
    id varchar(64) PRIMARY KEY,
    session_id varchar(64) NULL,
    scene varchar(32) NOT NULL,
    risk_level varchar(16) NOT NULL,
    blocked boolean NOT NULL DEFAULT false,
    hit_policies jsonb NOT NULL DEFAULT '[]'::jsonb,
    input_excerpt text NULL,
    response_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_session_risk_events_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL,
    CONSTRAINT chk_session_risk_events_scene CHECK (
        scene IN ('session_create', 'answer_generate', 'reflection_submit', 'manual_review')
    ),
    CONSTRAINT chk_session_risk_events_level CHECK (
        risk_level IN ('low', 'medium', 'high', 'critical')
    )
);

COMMENT ON TABLE session_risk_events IS '风险命中事件表，记录输入或输出安全拦截结果。';
COMMENT ON COLUMN session_risk_events.id IS '风险事件主键，建议使用 risk_ 前缀业务 ID。';
COMMENT ON COLUMN session_risk_events.session_id IS '关联会话 ID，可为空，兼容建会话前预检测。';
COMMENT ON COLUMN session_risk_events.scene IS '风险检测发生场景，如创建会话、生成答案、提交反思。';
COMMENT ON COLUMN session_risk_events.risk_level IS '本次命中的风险等级。';
COMMENT ON COLUMN session_risk_events.blocked IS '是否阻断了正常链路。';
COMMENT ON COLUMN session_risk_events.hit_policies IS '命中的风险策略列表，jsonb 数组格式。';
COMMENT ON COLUMN session_risk_events.input_excerpt IS '触发检测的输入摘要或截断文本。';
COMMENT ON COLUMN session_risk_events.response_payload IS '返回给前端的安全响应结构。';
COMMENT ON COLUMN session_risk_events.created_at IS '风险事件创建时间。';

CREATE INDEX IF NOT EXISTS idx_session_risk_events_session_id ON session_risk_events (session_id);
CREATE INDEX IF NOT EXISTS idx_session_risk_events_scene ON session_risk_events (scene);
CREATE INDEX IF NOT EXISTS idx_session_risk_events_risk_level ON session_risk_events (risk_level);

-- =========================================================
-- 10. session_event_logs
-- =========================================================
CREATE TABLE IF NOT EXISTS session_event_logs (
    id bigserial PRIMARY KEY,
    session_id varchar(64) NULL,
    event_name varchar(64) NOT NULL,
    event_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_session_event_logs_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
);

COMMENT ON TABLE session_event_logs IS '会话行为事件日志表，用于埋点、审计和问题排查。';
COMMENT ON COLUMN session_event_logs.id IS '自增主键。';
COMMENT ON COLUMN session_event_logs.session_id IS '关联会话 ID，可为空。';
COMMENT ON COLUMN session_event_logs.event_name IS '事件名称，如 session_draft_created、card_selected。';
COMMENT ON COLUMN session_event_logs.event_payload IS '事件扩展载荷，jsonb 格式。';
COMMENT ON COLUMN session_event_logs.created_at IS '事件记录时间。';

CREATE INDEX IF NOT EXISTS idx_session_event_logs_session_id ON session_event_logs (session_id);
CREATE INDEX IF NOT EXISTS idx_session_event_logs_event_name ON session_event_logs (event_name);
CREATE INDEX IF NOT EXISTS idx_session_event_logs_created_at ON session_event_logs (created_at DESC);

-- =========================================================
-- 10A. user_journal_weekly_snapshots
-- =========================================================
CREATE TABLE IF NOT EXISTS user_journal_weekly_snapshots (
    id varchar(64) PRIMARY KEY,
    user_id varchar(64) NOT NULL,
    week_start date NOT NULL,
    week_end date NOT NULL,
    summary_text text NOT NULL,
    top_emotions jsonb NOT NULL DEFAULT '[]'::jsonb,
    top_themes jsonb NOT NULL DEFAULT '[]'::jsonb,
    unfinished_actions integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_user_journal_weekly_snapshots_user_week UNIQUE (user_id, week_start),
    CONSTRAINT chk_user_journal_weekly_snapshots_unfinished CHECK (unfinished_actions >= 0),
    CONSTRAINT chk_user_journal_weekly_snapshots_range CHECK (week_end >= week_start)
);

COMMENT ON TABLE user_journal_weekly_snapshots IS '周度情绪回看聚合快照表，用于历史页和周报读取。';
COMMENT ON COLUMN user_journal_weekly_snapshots.id IS '周度快照主键，建议使用 weekly_ 前缀业务 ID。';
COMMENT ON COLUMN user_journal_weekly_snapshots.user_id IS '所属用户 ID。';
COMMENT ON COLUMN user_journal_weekly_snapshots.week_start IS '统计周起始日期。';
COMMENT ON COLUMN user_journal_weekly_snapshots.week_end IS '统计周结束日期。';
COMMENT ON COLUMN user_journal_weekly_snapshots.summary_text IS '周度摘要文本。';
COMMENT ON COLUMN user_journal_weekly_snapshots.top_emotions IS '高频情绪分布。';
COMMENT ON COLUMN user_journal_weekly_snapshots.top_themes IS '高频主题分布。';
COMMENT ON COLUMN user_journal_weekly_snapshots.unfinished_actions IS '未完成行动数量。';
COMMENT ON COLUMN user_journal_weekly_snapshots.created_at IS '快照生成时间。';

CREATE INDEX IF NOT EXISTS idx_user_journal_weekly_snapshots_user_week ON user_journal_weekly_snapshots (user_id, week_start DESC);

-- =========================================================
-- 11. daily_cards
-- =========================================================
CREATE TABLE IF NOT EXISTS daily_cards (
    id varchar(64) PRIMARY KEY,
    card_date date NOT NULL,
    name varchar(64) NOT NULL,
    description text NOT NULL,
    question_text text NOT NULL,
    theme varchar(32) NOT NULL,
    status varchar(16) NOT NULL DEFAULT 'published',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_daily_cards_card_date UNIQUE (card_date),
    CONSTRAINT chk_daily_cards_status CHECK (
        status IN ('draft', 'published', 'archived')
    )
);

COMMENT ON TABLE daily_cards IS '每日卡牌内容表，对应每日觉察卡页面。';
COMMENT ON COLUMN daily_cards.id IS '每日卡主键，建议使用 daily_yyyyMMdd 格式业务 ID。';
COMMENT ON COLUMN daily_cards.card_date IS '卡牌对应自然日日期。';
COMMENT ON COLUMN daily_cards.name IS '卡牌名称，如 观察、延迟、勇气。';
COMMENT ON COLUMN daily_cards.description IS '卡牌解释文案。';
COMMENT ON COLUMN daily_cards.question_text IS '今日提醒问题。';
COMMENT ON COLUMN daily_cards.theme IS '卡牌主题编码。';
COMMENT ON COLUMN daily_cards.status IS '卡牌发布状态。';
COMMENT ON COLUMN daily_cards.created_at IS '卡牌创建时间。';

CREATE INDEX IF NOT EXISTS idx_daily_cards_card_date ON daily_cards (card_date DESC);
CREATE INDEX IF NOT EXISTS idx_daily_cards_theme ON daily_cards (theme);

-- =========================================================
-- 12. user_pattern_snapshots
-- =========================================================
CREATE TABLE IF NOT EXISTS user_pattern_snapshots (
    id varchar(64) PRIMARY KEY,
    user_id varchar(64) NOT NULL,
    summary_text text NOT NULL,
    themes_payload jsonb NOT NULL DEFAULT '[]'::jsonb,
    emotions_payload jsonb NOT NULL DEFAULT '[]'::jsonb,
    card_preferences_payload jsonb NOT NULL DEFAULT '[]'::jsonb,
    decision_style_type varchar(64) NOT NULL,
    decision_style_label varchar(64) NOT NULL,
    decision_style_description text NOT NULL,
    sample_size integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_user_pattern_snapshots_sample_size CHECK (sample_size >= 0)
);

COMMENT ON TABLE user_pattern_snapshots IS '用户问题模式与决策风格分析快照表，对应洞察页。';
COMMENT ON COLUMN user_pattern_snapshots.id IS '快照主键，建议使用 snapshot_ 前缀业务 ID。';
COMMENT ON COLUMN user_pattern_snapshots.user_id IS '用户 ID。';
COMMENT ON COLUMN user_pattern_snapshots.summary_text IS '顶部摘要洞察文案。';
COMMENT ON COLUMN user_pattern_snapshots.themes_payload IS '主题分布数据，jsonb 数组格式。';
COMMENT ON COLUMN user_pattern_snapshots.emotions_payload IS '情绪分布数据，jsonb 数组格式。';
COMMENT ON COLUMN user_pattern_snapshots.card_preferences_payload IS '卡片偏好数据，jsonb 数组格式。';
COMMENT ON COLUMN user_pattern_snapshots.decision_style_type IS '决策风格编码。';
COMMENT ON COLUMN user_pattern_snapshots.decision_style_label IS '决策风格展示名称。';
COMMENT ON COLUMN user_pattern_snapshots.decision_style_description IS '决策风格解释说明。';
COMMENT ON COLUMN user_pattern_snapshots.sample_size IS '参与分析的历史样本量。';
COMMENT ON COLUMN user_pattern_snapshots.created_at IS '快照生成时间。';

CREATE INDEX IF NOT EXISTS idx_user_pattern_snapshots_user_created_at ON user_pattern_snapshots (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_pattern_snapshots_style_type ON user_pattern_snapshots (decision_style_type);

-- =========================================================
-- 13. users — 用户主表
-- =========================================================
CREATE TABLE IF NOT EXISTS users (
    id varchar(64) PRIMARY KEY,
    nickname varchar(128) NULL,
    avatar_style varchar(32) NULL,
    avatar_seed varchar(64) NULL,
    is_subscriber boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE users IS '用户主表。';
COMMENT ON COLUMN users.id IS '用户主键。';
COMMENT ON COLUMN users.nickname IS '用户昵称。';
COMMENT ON COLUMN users.avatar_style IS '头像风格。';
COMMENT ON COLUMN users.avatar_seed IS '头像随机种子。';
COMMENT ON COLUMN users.is_subscriber IS '是否订阅用户。';

CREATE INDEX IF NOT EXISTS idx_users_created_at ON users (created_at DESC);

-- =========================================================
-- 14. user_settings — 用户偏好设置表
-- =========================================================
CREATE TABLE IF NOT EXISTS user_settings (
    id varchar(64) PRIMARY KEY,
    user_id varchar(64) NOT NULL,
    preferred_mode varchar(32) NULL,
    language varchar(16) NOT NULL DEFAULT 'zh',
    notification_enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_user_settings_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT uq_user_settings_user UNIQUE (user_id)
);

COMMENT ON TABLE user_settings IS '用户偏好设置表。';
COMMENT ON COLUMN user_settings.id IS '设置主键。';
COMMENT ON COLUMN user_settings.user_id IS '所属用户 ID。';
COMMENT ON COLUMN user_settings.preferred_mode IS '偏好的照见模式。';
COMMENT ON COLUMN user_settings.language IS '界面语言。';
COMMENT ON COLUMN user_settings.notification_enabled IS '是否开启通知。';
COMMENT ON COLUMN user_settings.created_at IS '创建时间。';
COMMENT ON COLUMN user_settings.updated_at IS '更新时间。';

-- =========================================================
-- 14A. user_entitlements — 用户权益表
-- =========================================================
CREATE TABLE IF NOT EXISTS user_entitlements (
    id varchar(64) PRIMARY KEY,
    user_id varchar(64) NOT NULL,
    tier varchar(16) NOT NULL DEFAULT 'free',
    is_subscriber boolean NOT NULL DEFAULT false,
    ad_free boolean NOT NULL DEFAULT false,
    extra_question_quota integer NOT NULL DEFAULT 0,
    extra_cards_quota integer NOT NULL DEFAULT 0,
    remaining_reward_claims_today integer NOT NULL DEFAULT 0,
    unlocked_topics jsonb NOT NULL DEFAULT '[]'::jsonb,
    valid_until timestamptz NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_user_entitlements_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT uq_user_entitlements_user UNIQUE (user_id),
    CONSTRAINT chk_user_entitlements_tier CHECK (
        tier IN ('anonymous', 'free', 'subscriber')
    ),
    CONSTRAINT chk_user_entitlements_extra_question CHECK (extra_question_quota >= 0),
    CONSTRAINT chk_user_entitlements_extra_cards CHECK (extra_cards_quota >= 0),
    CONSTRAINT chk_user_entitlements_remaining_reward_claims CHECK (remaining_reward_claims_today >= 0),
    CONSTRAINT chk_user_entitlements_is_subscriber CHECK (
        (tier = 'subscriber' AND is_subscriber = true)
        OR (tier IN ('anonymous', 'free') AND is_subscriber = false)
    )
);

COMMENT ON TABLE user_entitlements IS '用户权益表，存储会员层级、去广告状态与激励解锁权益。';
COMMENT ON COLUMN user_entitlements.id IS '权益记录主键，建议使用 entitlement_ 前缀业务 ID。';
COMMENT ON COLUMN user_entitlements.user_id IS '所属用户 ID。';
COMMENT ON COLUMN user_entitlements.tier IS '用户层级，anonymous、free 或 subscriber。';
COMMENT ON COLUMN user_entitlements.is_subscriber IS '是否为订阅会员。';
COMMENT ON COLUMN user_entitlements.ad_free IS '是否默认去除大部分展示广告。';
COMMENT ON COLUMN user_entitlements.extra_question_quota IS '激励或活动额外赠送的提问次数。';
COMMENT ON COLUMN user_entitlements.extra_cards_quota IS '激励或活动额外赠送的卡片次数。';
COMMENT ON COLUMN user_entitlements.remaining_reward_claims_today IS '今日剩余可领取激励次数。';
COMMENT ON COLUMN user_entitlements.unlocked_topics IS '已解锁专题权益，jsonb 数组格式。';
COMMENT ON COLUMN user_entitlements.valid_until IS '权益有效期，空表示长期有效。';
COMMENT ON COLUMN user_entitlements.created_at IS '创建时间。';
COMMENT ON COLUMN user_entitlements.updated_at IS '更新时间。';

CREATE INDEX IF NOT EXISTS idx_user_entitlements_tier ON user_entitlements (tier);
CREATE INDEX IF NOT EXISTS idx_user_entitlements_valid_until ON user_entitlements (valid_until);

-- =========================================================
-- 15. global_stats — 全局统计缓存表
-- =========================================================
CREATE TABLE IF NOT EXISTS global_stats (
    id bigserial PRIMARY KEY,
    stat_key varchar(64) NOT NULL UNIQUE,
    stat_value bigint NOT NULL DEFAULT 0,
    refreshed_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE global_stats IS '全局统计缓存表，定期刷新。';

-- =========================================================
-- 16. llm_usage_logs — LLM 调用日志表
-- =========================================================
CREATE TABLE IF NOT EXISTS llm_usage_logs (
    id bigserial PRIMARY KEY,
    session_id varchar(64) NULL,
    provider varchar(64) NOT NULL,
    model varchar(128) NOT NULL,
    prompt_tokens integer NOT NULL DEFAULT 0,
    completion_tokens integer NOT NULL DEFAULT 0,
    cost_usd numeric(12,6) NULL,
    latency_ms integer NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE llm_usage_logs IS 'LLM 调用日志表，用于预算管控与审计。';

CREATE INDEX IF NOT EXISTS idx_llm_usage_logs_created_at ON llm_usage_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_usage_logs_session_id ON llm_usage_logs (session_id);

-- =========================================================
-- 17. idempotency_records — 幂等请求记录表
-- =========================================================
CREATE TABLE IF NOT EXISTS idempotency_records (
    id bigserial PRIMARY KEY,
    idempotency_key varchar(128) NOT NULL UNIQUE,
    status varchar(16) NOT NULL DEFAULT 'pending',
    response_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NULL
);

COMMENT ON TABLE idempotency_records IS '幂等请求记录表，防止重复提交。';

CREATE INDEX IF NOT EXISTS idx_idempotency_records_key ON idempotency_records (idempotency_key);

-- =========================================================
-- 18. user_quota_snapshots — 用户配额快照表
-- =========================================================
CREATE TABLE IF NOT EXISTS user_quota_snapshots (
    id varchar(64) PRIMARY KEY,
    user_id varchar(64) NOT NULL,
    quota_date date NOT NULL,
    daily_question_quota integer NOT NULL DEFAULT 0,
    daily_reflection_quota integer NOT NULL DEFAULT 0,
    remaining_question_quota integer NOT NULL DEFAULT 0,
    remaining_reflection_quota integer NOT NULL DEFAULT 0,
    source_breakdown jsonb NOT NULL DEFAULT '{}'::jsonb,
    quota_reset_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_user_quota_snapshots_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT uq_user_quota_snapshots_user_date UNIQUE (user_id, quota_date),
    CONSTRAINT chk_user_quota_snapshots_daily_question CHECK (daily_question_quota >= 0),
    CONSTRAINT chk_user_quota_snapshots_daily_reflection CHECK (daily_reflection_quota >= 0),
    CONSTRAINT chk_user_quota_snapshots_remaining_question CHECK (remaining_question_quota >= 0),
    CONSTRAINT chk_user_quota_snapshots_remaining_reflection CHECK (remaining_reflection_quota >= 0),
    CONSTRAINT chk_user_quota_snapshots_question_bounds CHECK (remaining_question_quota <= daily_question_quota),
    CONSTRAINT chk_user_quota_snapshots_reflection_bounds CHECK (remaining_reflection_quota <= daily_reflection_quota)
);

COMMENT ON TABLE user_quota_snapshots IS '用户配额快照表，用于记录每日提问与多轮反思额度。';
COMMENT ON COLUMN user_quota_snapshots.id IS '配额快照主键，建议使用 quota_ 前缀业务 ID。';
COMMENT ON COLUMN user_quota_snapshots.user_id IS '所属用户 ID。';
COMMENT ON COLUMN user_quota_snapshots.quota_date IS '配额所属自然日。';
COMMENT ON COLUMN user_quota_snapshots.daily_question_quota IS '当日正式提问总额度。';
COMMENT ON COLUMN user_quota_snapshots.daily_reflection_quota IS '当日多轮反思总额度。';
COMMENT ON COLUMN user_quota_snapshots.remaining_question_quota IS '当日剩余正式提问额度。';
COMMENT ON COLUMN user_quota_snapshots.remaining_reflection_quota IS '当日剩余多轮反思额度。';
COMMENT ON COLUMN user_quota_snapshots.source_breakdown IS '基础配额、订阅增量、激励增量的来源拆分。';
COMMENT ON COLUMN user_quota_snapshots.quota_reset_at IS '下次额度重置时间。';
COMMENT ON COLUMN user_quota_snapshots.created_at IS '创建时间。';
COMMENT ON COLUMN user_quota_snapshots.updated_at IS '更新时间。';

CREATE INDEX IF NOT EXISTS idx_user_quota_snapshots_user_id ON user_quota_snapshots (user_id, quota_date DESC);
CREATE INDEX IF NOT EXISTS idx_user_quota_snapshots_quota_reset_at ON user_quota_snapshots (quota_reset_at);

-- =========================================================
-- 19. 可选更新时间触发器
-- =========================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION set_updated_at() IS '通用更新时间触发器函数，用于自动维护 updated_at 字段。';

DROP TRIGGER IF EXISTS trg_sessions_set_updated_at ON sessions;
CREATE TRIGGER trg_sessions_set_updated_at
BEFORE UPDATE ON sessions
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_session_unload_drafts_set_updated_at ON session_unload_drafts;
CREATE TRIGGER trg_session_unload_drafts_set_updated_at
BEFORE UPDATE ON session_unload_drafts
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_session_resume_snapshots_set_updated_at ON session_resume_snapshots;
CREATE TRIGGER trg_session_resume_snapshots_set_updated_at
BEFORE UPDATE ON session_resume_snapshots
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_users_set_updated_at ON users;
CREATE TRIGGER trg_users_set_updated_at
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_user_settings_set_updated_at ON user_settings;
CREATE TRIGGER trg_user_settings_set_updated_at
BEFORE UPDATE ON user_settings
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_user_entitlements_set_updated_at ON user_entitlements;
CREATE TRIGGER trg_user_entitlements_set_updated_at
BEFORE UPDATE ON user_entitlements
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_user_quota_snapshots_set_updated_at ON user_quota_snapshots;
CREATE TRIGGER trg_user_quota_snapshots_set_updated_at
BEFORE UPDATE ON user_quota_snapshots
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

COMMIT;
