# routes/api.py
from flask import Blueprint, request, jsonify, send_file
from bot_service import BotService
from database import ChannelRepository, RecordingRepository
import logging
import os

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')


def init_routes(bot_service: BotService,
                channel_repo: ChannelRepository,
                recording_repo: RecordingRepository):

    @api_bp.route('/bot/status', methods=['GET'])
    def get_bot_status():
        status = bot_service.get_status()
        return jsonify({
            'state': status.state.value,
            'connected_channel': status.connected_channel,
            'is_transmitting': status.is_transmitting,
            'current_speakers': status.current_speakers,
            'error_message': status.error_message
        })

    @api_bp.route('/bot/start', methods=['POST'])
    def start_bot():
        success = bot_service.start()
        return jsonify({'success': success})

    @api_bp.route('/bot/stop', methods=['POST'])
    def stop_bot():
        bot_service.stop()
        return jsonify({'success': True})

    @api_bp.route('/channels', methods=['GET'])
    def list_channels():
        config_channels = channel_repo.list_all()
        bsht_channels = bot_service.get_channels()

        result = []
        for bsht_ch in bsht_channels:
            config = next((c for c in config_channels if c.channel_id == bsht_ch.channel_id), None)
            result.append({
                'channel_id': bsht_ch.channel_id,
                'name': bsht_ch.name,
                'auto_join': config.auto_join if config else False,
                'auto_record': config.auto_record if config else True,
                'configured': config is not None
            })
        return jsonify(result)

    @api_bp.route('/channels', methods=['POST'])
    def add_channel():
        from database import Channel
        data = request.json
        channel = Channel(
            channel_id=data.get('channel_id'),
            name=data.get('name', ''),
            passcode=data.get('passcode', 0),
            auto_join=data.get('auto_join', False),
            auto_record=data.get('auto_record', True)
        )
        channel_id = channel_repo.add(channel)
        return jsonify({'success': True, 'id': channel_id})

    @api_bp.route('/channels/<int:channel_id>', methods=['DELETE'])
    def delete_channel(channel_id: int):
        success = channel_repo.delete(channel_id)
        return jsonify({'success': success})

    @api_bp.route('/channels/<int:channel_id>/join', methods=['POST'])
    def join_channel(channel_id: int):
        passcode = request.json.get('passcode', 0) if request.json else 0
        success = bot_service.join_channel(channel_id, passcode)
        return jsonify({'success': success})

    @api_bp.route('/channels/leave', methods=['POST'])
    def leave_channel():
        bot_service.leave_channel()
        return jsonify({'success': True})

    @api_bp.route('/ptt/start', methods=['POST'])
    def start_ptt():
        success = bot_service.start_transmit()
        return jsonify({'success': success})

    @api_bp.route('/ptt/stop', methods=['POST'])
    def stop_ptt():
        success = bot_service.stop_transmit()
        return jsonify({'success': success})

    @api_bp.route('/recordings', methods=['GET'])
    def list_recordings():
        channel_id = request.args.get('channel_id', type=int)
        limit = request.args.get('limit', 100, type=int)

        if channel_id:
            recordings = recording_repo.list_by_channel(channel_id, limit)
        else:
            recordings = recording_repo.list(limit)

        result = []
        for rec in recordings:
            result.append({
                'id': rec.id,
                'channel_id': rec.channel_id,
                'file_path': rec.file_path,
                'speaker_name': rec.speaker_name,
                'start_time': rec.start_time.isoformat() if rec.start_time else None,
                'duration_sec': round(rec.duration_sec, 2),
                'frames': rec.frames,
                'loss_rate': round(rec.loss_rate, 4),
                'transcription': rec.transcription
            })
        return jsonify(result)

    @api_bp.route('/recordings/<int:recording_id>', methods=['GET'])
    def get_recording(recording_id: int):
        rec = recording_repo.get_by_id(recording_id)
        if not rec:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({
            'id': rec.id,
            'channel_id': rec.channel_id,
            'file_path': rec.file_path,
            'speaker_name': rec.speaker_name,
            'start_time': rec.start_time.isoformat() if rec.start_time else None,
            'duration_sec': rec.duration_sec
        })

    @api_bp.route('/recordings/<int:recording_id>', methods=['DELETE'])
    def delete_recording(recording_id: int):
        rec = recording_repo.get_by_id(recording_id)
        if rec:
            try:
                if os.path.exists(rec.file_path):
                    os.remove(rec.file_path)
            except Exception as e:
                logger.warning(f"删除文件失败: {e}")
            success = recording_repo.delete(recording_id)
            return jsonify({'success': success})
        return jsonify({'success': False})

    @api_bp.route('/recordings/<int:recording_id>/download', methods=['GET'])
    def download_recording(recording_id: int):
        rec = recording_repo.get_by_id(recording_id)
        if not rec or not os.path.exists(rec.file_path):
            return jsonify({'error': 'File not found'}), 404
        return send_file(
            rec.file_path,
            mimetype='audio/wav',
            as_attachment=True,
            download_name=f"{rec.speaker_name}_{rec.start_time.strftime('%Y%m%d_%H%M%S')}.wav" if rec.start_time else "recording.wav"
        )

    return api_bp
