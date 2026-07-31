# Política de Seguridad

## Reportar Vulnerabilidades de Seguridad

**Por favor NO reportes vulnerabilidades de seguridad a través de GitHub Issues públicos.**

En su lugar, envía un email a: **dev@tupensioninteligente.cl** con:

1. **Descripción** de la vulnerabilidad
2. **Pasos** para reproducirla
3. **Impacto potencial**
4. Tus datos de contacto

Nos comprometemos a:
- Reconocer recepción en 48 horas
- Investigar el issue
- Contactarte con actualizaciones
- Crédito público si lo deseas

## Prácticas de Seguridad

### Datos Sensibles

- ❌ **NUNCA** commitees credenciales o secrets
- ✅ Usa `.env` y `.env.example`
- ✅ Configura secretos en variables de entorno
- ✅ Usa `python-dotenv` para desarrollo

### Dependencias

- Revisamos regularmente vulnerabilidades
- Actualizamos dependencias periódicamente
- Usamos `pip-audit` para detectar vulnerabilidades

```bash
pip install pip-audit
pip-audit
```

### Database

- Queries parametrizadas (SQLAlchemy ORM)
- Validación de entrada con Pydantic
- Sanitización de datos personales
- No loguees información sensible

### Validación

- Valida todos los inputs
- Usa tipos estrictos (Pydantic)
- Implementa rate limiting en producción
- Usa HTTPS en producción

## Seguridad en Deployments

### Antes de Producción

- [ ] Cambiar todas las contraseñas por defecto
- [ ] Configurar HTTPS
- [ ] Activar autenticación
- [ ] Configurar CORS adecuadamente
- [ ] Configurar logs de auditoría
- [ ] Realizar penetration testing
- [ ] Audit de código de seguridad

### Variables de Entorno Críticas

```bash
# Debe cambiar TODAS en producción
APP_ENV=production
DATABASE_HOST=<production-host>
DATABASE_USER=<strong-user>
DATABASE_PASSWORD=<strong-password>
SECRET_KEY=<generated-secure-key>
```

## Dependency Management

```bash
# Ver dependencias con vulnerabilidades conocidas
pip list

# Actualizar dependencias seguras
pip install --upgrade -e ".[dev]"
```

## Más Información

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Python Security](https://python.readthedocs.io/en/latest/library/security_warnings.html)
- [Streamlit Security](https://docs.streamlit.io/library/advanced-features/security)

---

Gracias por ayudar a mantener nuestro proyecto seguro.
