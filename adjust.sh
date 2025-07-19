# app 目录
mv app.py app/main.py

# core 目录
mv baseasr.py core/asr/
mv museasr.py core/asr/
mv lipasr.py core/asr/
mv musereal.py core/models/musereal/
mv lightreal.py core/models/lightreal/
mv lipreal.py core/models/lipreal/
mv ttsreal.py core/tts/
mv llm.py core/llm/
mv llm_coze.py core/llm/
mv webrtc.py core/webrtc/

# web 目录
mv web/*.html web/templates/
mv web/*.js web/static/

# scripts 目录
#mv start_musetalk_v15.sh scripts/
#mv start_musetalk_v15.sh.example scripts/

# utils 目录
mv logger.py utils/
