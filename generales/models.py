from django.db import models

class SurveyResponse(models.Model):
    created_at = models.DateTimeField()
    data = models.JSONField()
    survey_question_id = models.BigIntegerField()
    survey_user_id = models.BigIntegerField()

    class Meta:
        db_table = 'encuesta_respuestas'
        
class EncuestaRespuesta(models.Model):
    survey_question_id = models.IntegerField()
    survey_user_id = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    data = models.JSONField()

    class Meta:
        db_table = 'encuestas_respuestas'
        
class SurveyResult(models.Model):
    id = models.AutoField(primary_key=True)
    survey_id = models.IntegerField()
    vivienda = models.CharField(max_length=100)
    sector = models.CharField(max_length=100)
    persona = models.CharField(max_length=200)

    class Meta:
        managed = False   # 🔒 Django no creará ni borrará la tabla
        db_table = 'encuestas'   # ⚠️ pon aquí el nombre real de la tabla