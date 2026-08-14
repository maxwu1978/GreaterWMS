from django.db import models

class ListModel(models.Model):
    staff_name = models.CharField(max_length=255, verbose_name="Staff Name")
    staff_type = models.CharField(max_length=255, verbose_name="Staff Type")
    check_code = models.IntegerField(default=8888, verbose_name="Check Code")
    openid = models.CharField(max_length=255, verbose_name="Openid")
    is_delete = models.BooleanField(default=False, verbose_name='Delete Label')
    create_time = models.DateTimeField(auto_now_add=True, verbose_name="Create Time")
    update_time = models.DateTimeField(auto_now=True, blank=True, null=True, verbose_name="Update Time")
    error_check_code_counter = models.IntegerField(default=0,verbose_name='check_code error counter')
    is_lock = models.BooleanField(default=False,verbose_name='Whether the lock')
    class Meta:
        db_table = 'staff'
        verbose_name = 'Staff'
        verbose_name_plural = "Staff"
        ordering = ['staff_name']


class StaffSessionToken(models.Model):
    """Opaque API session bound to exactly one staff record."""

    TOKEN_KINDS = (
        ('admin', 'Administrator'),
        ('staff', 'Staff'),
    )

    staff_id = models.BigIntegerField(db_index=True)
    openid = models.CharField(max_length=255, db_index=True)
    token_hash = models.CharField(max_length=64, unique=True)
    token_kind = models.CharField(max_length=16, choices=TOKEN_KINDS, default='staff')
    is_revoked = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'staff_session_token'
        indexes = [
            models.Index(fields=['staff_id', 'is_revoked']),
            models.Index(fields=['openid', 'is_revoked']),
        ]

class TypeListModel(models.Model):
    staff_type = models.CharField(max_length=255, verbose_name="Staff Type")
    openid = models.CharField(max_length=255, verbose_name="Openid")
    creater = models.CharField(max_length=255, verbose_name="Creater")
    create_time = models.DateTimeField(auto_now_add=True, verbose_name="Create Time")
    update_time = models.DateTimeField(auto_now=True, blank=True, null=True, verbose_name="Update Time")

    class Meta:
        db_table = 'stafftype'
        verbose_name = 'Staff Type'
        verbose_name_plural = "Staff Type"
        ordering = ['staff_type']
